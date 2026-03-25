"""ASR 引擎 — 通过 HTTP API 调用语音识别。

支持：
- whisper-asr-webservice（POST /asr）
- OpenAI Whisper API（POST /v1/audio/transcriptions）
- 通过 base_url 自动识别

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

        prompt = None
        if hotwords:
            prompt = "以下是本次对话可能涉及的人名和术语：" + "、".join(hotwords) + "。"
            logger.info("使用自定义术语: %s", prompt)

        try:
            # 判断 API 类型：base_url 含 /v1 → OpenAI 格式，否则 → webservice 格式
            if "/v1" in self._base_url:
                result = self._call_openai(audio_path, lang, prompt)
            else:
                result = self._call_webservice(audio_path, lang, prompt)
        except httpx.ConnectError:
            raise RuntimeError(
                f"ASR 服务未启动或不可达: {self._base_url}。"
                f"请检查 whisper 容器: docker ps | grep whisper"
            ) from None
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"ASR 服务返回错误 {e.response.status_code}: {e.response.text[:200]}"
            ) from None

        segments = self._parse_response(result)
        logger.info("转写完成: %d 个片段, 语言=%s", len(segments), lang)
        return segments

    def _call_openai(self, audio_path: Path, lang: str, prompt: str | None) -> dict:
        """OpenAI Whisper API 格式: POST {base_url}/audio/transcriptions"""
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/wav")}
            data = {"model": self._model, "language": lang, "response_format": "verbose_json"}
            if prompt:
                data["prompt"] = prompt
            with httpx.Client(timeout=600.0) as client:
                resp = client.post(
                    f"{self._base_url}/audio/transcriptions",
                    files=files, data=data,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                return resp.json()

    def _call_webservice(self, audio_path: Path, lang: str, prompt: str | None) -> dict:
        """whisper-asr-webservice 格式: POST {base_url}/asr"""
        with open(audio_path, "rb") as f:
            files = {"audio_file": (audio_path.name, f, "audio/wav")}
            params = {
                "language": lang,
                "output": "json",
                "word_timestamps": "true",
                "vad_filter": "true",
            }
            if prompt:
                params["initial_prompt"] = prompt
            with httpx.Client(timeout=600.0) as client:
                resp = client.post(
                    f"{self._base_url}/asr",
                    files=files, params=params,
                )
                resp.raise_for_status()
                return resp.json()

    @staticmethod
    def _parse_response(result: dict) -> list[Segment]:
        """解析响应为 Segment 列表。兼容 OpenAI 和 webservice 两种格式。"""
        segments = []
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
        if not segments and result.get("text"):
            segments.append(Segment(
                start=0.0, end=result.get("duration", 0.0),
                text=result["text"].strip(), speaker_id="",
            ))
        return segments
