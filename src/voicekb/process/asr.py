"""ASR 引擎 — 基于 faster-whisper 的语音识别，支持自定义术语。"""

import logging
from pathlib import Path

from faster_whisper import WhisperModel

from voicekb.models import Segment

logger = logging.getLogger(__name__)


class ASREngine:
    """Whisper ASR 引擎，封装 faster-whisper。"""

    def __init__(self, model_size: str = "small", device: str = "cuda",
                 compute_type: str = "float16") -> None:
        # CPU 不支持 float16，自动降级
        if device == "cpu" and compute_type == "float16":
            compute_type = "int8"
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None  # 懒加载，首次使用时才占 GPU 显存

    def _ensure_model(self):
        if self._model is None:
            logger.info("加载 Whisper 模型: %s (device=%s, compute=%s)",
                        self._model_size, self._device, self._compute_type)
            self._model = WhisperModel(self._model_size, device=self._device,
                                       compute_type=self._compute_type)
            logger.info("Whisper 模型加载完成")

    def transcribe(self, audio_path: Path, language: str = "zh",
                   hotwords: list[str] | None = None) -> list[Segment]:
        """转写音频文件，返回带时间戳的文本段列表。

        Args:
            hotwords: 自定义术语列表（人名、专业术语等），提高识别准确率。
        """
        self._ensure_model()
        logger.info("开始转写: %s", audio_path.name)

        # 将术语列表注入 initial_prompt，引导模型使用正确用词
        initial_prompt = None
        if hotwords:
            initial_prompt = "以下是本次对话可能涉及的人名和术语：" + "、".join(hotwords) + "。"
            logger.info("使用自定义术语: %s", initial_prompt)

        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            initial_prompt=initial_prompt,
        )

        result: list[Segment] = []
        for seg in segments_iter:
            result.append(Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                speaker_id="",
                confidence=seg.avg_logprob,
            ))

        logger.info("转写完成: %d 个片段, 语言=%s (%.1f%%)",
                     len(result), info.language, info.language_probability * 100)
        return result
