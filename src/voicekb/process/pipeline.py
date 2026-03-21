"""处理管道 — 编排 ASR + 声纹分离 + 说话人匹配。"""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from voicekb.config import Settings
from voicekb.models import Recording, Segment
from voicekb.process.asr import ASREngine
from voicekb.process.diarize import Diarizer
from voicekb.process.speaker_db import SpeakerDB

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int], None] | None


class ProcessingPipeline:
    """音频处理管道：ASR → 声纹分离 → 说话人匹配 → 结构化输出。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._asr: ASREngine | None = None
        self._diarizer: Diarizer | None = None
        self._speaker_db: SpeakerDB | None = None

    def _ensure_models(self) -> None:
        """懒加载模型，避免启动时占用全部显存。"""
        if self._asr is None:
            self._asr = ASREngine(
                model_size=self._settings.whisper_model,
                device=self._settings.whisper_device,
                compute_type=self._settings.whisper_compute_type,
            )
        if self._diarizer is None:
            self._diarizer = Diarizer()
        if self._speaker_db is None:
            self._speaker_db = SpeakerDB(self._settings.speaker_db_path)

    @property
    def speaker_db(self) -> SpeakerDB:
        if self._speaker_db is None:
            self._speaker_db = SpeakerDB(self._settings.speaker_db_path)
        return self._speaker_db

    def process(self, audio_path: Path, recording_id: str,
                progress_cb: ProgressCallback = None) -> Recording:
        """处理单个音频文件，返回完整的 Recording 对象。

        步骤：
        1. ASR 转写 (0-40%)
        2. 声纹分离 (40-70%)
        3. 对齐 ASR 和声纹标签 (70-80%)
        4. 说话人匹配/注册 (80-95%)
        5. 完成 (95-100%)
        """
        self._ensure_models()
        assert self._asr is not None
        assert self._diarizer is not None
        assert self._speaker_db is not None

        def _progress(step: str, pct: int) -> None:
            if progress_cb:
                progress_cb(step, pct)
            logger.info("[%s] %s: %d%%", recording_id, step, pct)

        _progress("开始处理", 0)

        # Step 1: ASR
        _progress("语音识别", 5)
        asr_segments = self._asr.transcribe(audio_path)
        _progress("语音识别完成", 40)

        # Step 2: 声纹分离
        _progress("声纹分离", 45)
        speaker_segments = self._diarizer.diarize(audio_path)
        _progress("声纹分离完成", 70)

        # Step 3: 对齐 — 将声纹标签分配给 ASR 片段
        _progress("对齐标签", 75)
        labeled_segments = self._align_segments(asr_segments, speaker_segments)
        _progress("对齐完成", 80)

        # Step 4: 匹配/注册说话人
        _progress("匹配说话人", 85)
        final_segments, speakers = self._match_speakers(
            labeled_segments, speaker_segments, recording_id,
        )
        _progress("匹配完成", 95)

        # 计算时长
        duration = 0.0
        if final_segments:
            duration = max(s.end for s in final_segments)

        recording = Recording(
            id=recording_id,
            filename=audio_path.name,
            source="upload",
            duration=duration,
            created_at=datetime.now(),
            status="completed",
            segments=final_segments,
            speakers=speakers,
        )

        _progress("处理完成", 100)
        return recording

    def _align_segments(
        self,
        asr_segments: list[Segment],
        speaker_segments: list,
    ) -> list[Segment]:
        """将声纹标签对齐到 ASR 片段。

        策略：对每个 ASR 片段，找时间重叠最大的声纹段。
        """
        result: list[Segment] = []

        for seg in asr_segments:
            mid_time = (seg.start + seg.end) / 2
            best_label = "SPEAKER_00"
            best_overlap = 0.0

            for spk_seg in speaker_segments:
                overlap_start = max(seg.start, spk_seg.start)
                overlap_end = min(seg.end, spk_seg.end)
                overlap = max(0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_label = spk_seg.speaker_label

            result.append(Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker_id=best_label,
                confidence=seg.confidence,
            ))

        return result

    def _match_speakers(
        self,
        segments: list[Segment],
        speaker_segments: list,
        recording_id: str,
    ) -> tuple[list[Segment], list[str]]:
        """将聚类标签映射到已注册的说话人或注册新说话人。"""
        assert self._diarizer is not None
        assert self._speaker_db is not None

        # 收集每个聚类标签的质心
        label_set = sorted(set(s.speaker_id for s in segments))
        label_to_name: dict[str, str] = {}
        speaker_names: list[str] = []

        for label in label_set:
            centroid = self._diarizer.compute_centroid(speaker_segments, label)

            # 尝试匹配已注册说话人
            matched = self._speaker_db.match_speaker(
                centroid, self._settings.speaker_similarity_threshold,
            )

            if matched:
                label_to_name[label] = matched.name
                self._speaker_db.add_recording_to_speaker(
                    matched.id, recording_id,
                )
                # 更新嵌入（滑动平均）
                self._speaker_db.update_embedding(matched.id, centroid)
                logger.info("已识别说话人: %s -> %s", label, matched.name)
            else:
                # 注册为新说话人
                new_name = label  # 保持 SPEAKER_XX，用户可后续标注
                new_spk = self._speaker_db.register_speaker(
                    new_name, centroid, recording_id,
                )
                label_to_name[label] = new_spk.name
                logger.info("新说话人: %s -> %s", label, new_spk.name)

            speaker_names.append(label_to_name[label])

        # 替换所有片段中的标签
        final = []
        for seg in segments:
            final.append(Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker_id=label_to_name.get(seg.speaker_id, seg.speaker_id),
                confidence=seg.confidence,
            ))

        return final, sorted(set(speaker_names))
