"""声纹分离 — pyannote.audio 3.1 神经网络 pipeline。"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """一个带说话人标签的时间段。"""
    start: float
    end: float
    speaker_label: str  # "SPEAKER_00", "SPEAKER_01", ...
    embedding: np.ndarray


class Diarizer:
    """声纹分离引擎（pyannote.audio 3.1）。"""

    def __init__(self) -> None:
        from pyannote.audio import Pipeline

        logger.info("加载声纹模型 (pyannote.audio 3.1)...")
        self._pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._pipeline.to(device)
        logger.info("声纹模型加载完成 (device=%s)", device)

    def diarize(self, audio_path: Path,
                num_speakers: int | None = None,
                **kwargs) -> list[SpeakerSegment]:
        """对音频进行声纹分离。

        Args:
            audio_path: 音频文件路径
            num_speakers: 说话人数量（None=自动检测）
        """
        # 非 wav 16kHz 文件先转换，避免 pyannote 采样数校验失败
        actual_path = Diarizer._ensure_wav16k(audio_path)

        # 构建 pipeline 参数
        params = {}
        if num_speakers is not None:
            params["num_speakers"] = num_speakers

        result = self._pipeline(str(actual_path), **params)

        # 清理临时转换文件
        if actual_path != audio_path and actual_path.exists():
            actual_path.unlink()

        # pyannote v4: result.speaker_diarization (Annotation) + result.speaker_embeddings (ndarray)
        annotation = result.speaker_diarization
        embeddings_matrix = result.speaker_embeddings  # shape: (num_speakers, 256)

        # 构建每个说话人标签到 embedding 的映射
        labels = annotation.labels()
        label_to_embedding = {}
        for i, label in enumerate(labels):
            if i < len(embeddings_matrix):
                label_to_embedding[label] = embeddings_matrix[i]
            else:
                label_to_embedding[label] = np.zeros(256)

        logger.info("声纹分离: %d 个说话人, %d 个片段",
                     len(labels), len(list(annotation.itertracks())))

        # 转换为 SpeakerSegment 列表
        segments: list[SpeakerSegment] = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segments.append(SpeakerSegment(
                start=turn.start,
                end=turn.end,
                speaker_label=speaker,
                embedding=label_to_embedding.get(speaker, np.zeros(256)),
            ))

        return segments

    @staticmethod
    def _ensure_wav16k(audio_path: Path) -> Path:
        """确保音频是 16kHz wav 格式，否则用 ffmpeg 转换。"""
        import subprocess
        if audio_path.suffix.lower() == ".wav":
            # 检查是否已经是 16kHz
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.stdout.strip() == "16000":
                    return audio_path
            except Exception:
                pass  # ffprobe 不可用，走后面的转换逻辑

        # 转换为 16kHz wav
        out_path = audio_path.parent / f"{audio_path.stem}_16k.wav"
        if out_path.exists():
            return out_path
        logger.info("转换音频为 16kHz wav: %s", audio_path.name)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-ar", "16000", "-ac", "1", str(out_path)],
            capture_output=True, timeout=120,
        )
        return out_path

    def compute_centroid(self, segments: list[SpeakerSegment],
                         label: str) -> np.ndarray:
        """计算某个说话人标签的嵌入质心。

        pyannote 已经输出了每个说话人的全局 embedding，
        直接取第一个匹配的 segment 的 embedding（它们都一样）。
        """
        for seg in segments:
            if seg.speaker_label == label:
                return seg.embedding
        return np.zeros(256)

    def extract_embedding(self, audio_path: Path,
                          start: float, end: float) -> np.ndarray:
        """从音频的指定时间范围提取说话人嵌入。

        pyannote 不支持单段提取，用整段 diarize 结果中最近的 segment。
        实际场景中这个方法很少被调用。
        """
        segments = self.diarize(audio_path)
        # 找时间最接近的 segment
        best = None
        best_overlap = 0
        for seg in segments:
            overlap = min(end, seg.end) - max(start, seg.start)
            if overlap > best_overlap:
                best_overlap = overlap
                best = seg
        return best.embedding if best else np.zeros(256)
