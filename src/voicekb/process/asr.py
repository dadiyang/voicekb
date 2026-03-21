"""ASR 引擎 — 基于 faster-whisper 的语音识别。"""

import logging
from pathlib import Path

from faster_whisper import WhisperModel

from voicekb.models import Segment

logger = logging.getLogger(__name__)


class ASREngine:
    """Whisper ASR 引擎，封装 faster-whisper。"""

    def __init__(self, model_size: str = "small", device: str = "cuda",
                 compute_type: str = "float16") -> None:
        logger.info("加载 Whisper 模型: %s (device=%s)", model_size, device)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Whisper 模型加载完成")

    def transcribe(self, audio_path: Path, language: str = "zh") -> list[Segment]:
        """转写音频文件，返回带时间戳的文本段列表。"""
        logger.info("开始转写: %s", audio_path.name)

        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        result: list[Segment] = []
        for seg in segments_iter:
            result.append(Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                speaker_id="",  # 待声纹分离后填充
                confidence=seg.avg_logprob,
            ))

        logger.info("转写完成: %d 个片段, 语言=%s (%.1f%%)",
                     len(result), info.language, info.language_probability * 100)
        return result
