"""LLM 适配器 — 可插拔的大语言模型后端。"""

import logging
from typing import Protocol

import httpx

from voicekb.config import Settings

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    """LLM 后端协议。"""

    async def generate(self, prompt: str, max_tokens: int = 2000) -> str: ...


class OpenAICompatibleLLM:
    """兼容 OpenAI API 的 LLM 后端（vLLM, Ollama 等）。"""

    def __init__(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.3,
                    },
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # 去掉 Qwen3 的 <think>...</think> 思考过程
                import re
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return content
        except Exception:
            logger.error("LLM 生成失败", exc_info=True)
            return ""


class NoLLM:
    """空 LLM — 当未配置 LLM 时使用。"""

    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        return ""


def create_llm(settings: Settings) -> LLMBackend:
    """根据配置创建 LLM 后端。"""
    if settings.llm_backend == "none":
        logger.info("LLM 未配置，使用 NoLLM")
        return NoLLM()

    logger.info("使用 OpenAI 兼容 LLM: %s (%s)", settings.llm_base_url, settings.llm_model)
    return OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
    )
