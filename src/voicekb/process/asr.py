"""ASR 引擎 — 通过 OpenAI Whisper API 兼容接口调用语音识别。

支持任何实现 /v1/audio/transcriptions 的服务：
- 本地 faster-whisper-server（speaches）
- OpenAI Whisper API
- 阿里云/其他云端 ASR（需兼容 OpenAI 格式）

voicekb 进程不加载任何模型，零 GPU 依赖。
"""

import logging
from pathlib import Path

import httpx

from voicekb.models import Segment

logger = logging.getLogger(__name__)


class ASREngine:
    """Whisper ASR 引擎，通过 HTTP API 调用。"""

    def __init__(self, base_url: str = "http://localhost:8000/v1",
                 model: str = "medium", api_key: str = "not-needed",
                 language: str = "zh") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._language = language

    def transcribe(self, audio_path: Path, language: str | None = None,
                   hotwords: list[str] | None = None) -> list[Segment]:
        """转写音频文件，返回带时间戳的文本段列表。"""
        lang = language or self._language
        logger.info("开始转写: %s (model=%s, lang=%s, api=%s)",
                    audio_path.name, self._model, lang, self._base_url)

        # 构建 initial_prompt（术语引导）
        prompt = None
        if hotwords:
            prompt = "以下是本次对话可能涉及的人名和术语：" + "、".join(hotwords) + "。"
            logger.info("使用自定义术语: %s", prompt)

        # 调用 OpenAI Whisper API 兼容接口
        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path.name, f, "audio/wav")}
                data = {
                    "model": self._model,
                    "language": lang,
                    "response_format": "verbose_json",
                }
                if prompt:
                    data["prompt"] = prompt

                with httpx.Client(timeout=600.0) as client:
                    resp = client.post(
                        f"{self._base_url}/audio/transcriptions",
                        files=files,
                        data=data,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
                    resp.raise_for_status()
                    result = resp.json()
        except httpx.ConnectError:
            raise RuntimeError(
                f"ASR 服务未启动或不可达: {self._base_url}。"
                f"请检查 whisper 容器是否运行: docker ps | grep whisper"
            ) from None
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"ASR 服务返回错误 {e.response.status_code}: {e.response.text[:200]}") from None

        # 解析响应（OpenAI verbose_json 格式）
        segments = self._parse_response(result)
        logger.info("转写完成: %d 个片段, 语言=%s", len(segments), lang)
        return segments

    @staticmethod
    def _parse_response(result: dict) -> list[Segment]:
        """解析 OpenAI Whisper API verbose_json 响应为 Segment 列表。"""
        segments = []

        # verbose_json 格式有 segments 字段
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            segments.append(Segment(
                start=seg.get("start", 0.0),
                end=seg.get("end", 0.0),
                text=text,
                speaker_id="",
                confidence=seg.get("avg_logprob", 0.0),
            ))

        # 如果没有 segments（某些 API 只返回 text），创建单个 segment
        if not segments and result.get("text"):
            segments.append(Segment(
                start=0.0,
                end=result.get("duration", 0.0),
                text=result["text"].strip(),
                speaker_id="",
            ))

        return segments
