"""LLM 适配器 — 可插拔的大语言模型后端，支持多轮对话。"""

import json as _json
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

import httpx

from voicekb.config import Settings

logger = logging.getLogger(__name__)

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": "..."}


@dataclass
class LLMResponse:
    """LLM 回复，区分思考过程和最终回答。"""
    content: str = ""
    reasoning: str = ""


class LLMBackend(Protocol):
    """LLM 后端协议。"""

    async def chat(self, messages: list[Message], max_tokens: int = 2000,
                   deep_think: bool = False) -> LLMResponse: ...


class OpenAICompatibleLLM:
    """兼容 OpenAI API 的 LLM 后端（vLLM, Ollama 等）。"""

    def __init__(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def chat(self, messages: list[Message], max_tokens: int = 2000,
                   temperature: float = 0.3, deep_think: bool = False) -> LLMResponse:
        try:
            body: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
            }

            if deep_think:
                # 深度思考：开启 thinking，给足 token 空间
                body["max_tokens"] = 24000
            else:
                # 快速回答：禁用 thinking，节省 token
                body["max_tokens"] = max_tokens
                body["chat_template_kwargs"] = {"enable_thinking": False}

            async with httpx.AsyncClient(timeout=300.0 if deep_think else 120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning") or ""

                # 兼容 <think> tag 写法（部分模型不走 reasoning 字段）
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                if "<think>" in content:
                    content = content.split("<think>")[0]

                return LLMResponse(content=content.strip(), reasoning=reasoning.strip())
        except Exception:
            logger.error("LLM 生成失败", exc_info=True)
            return LLMResponse()

    async def chat_stream(self, messages: list[Message], max_tokens: int = 2000,
                          temperature: float = 0.3, deep_think: bool = False):
        """流式生成，yield (phase, delta) 元组。phase 为 'reasoning' 或 'content'。"""
        body: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if deep_think:
            body["max_tokens"] = 24000
        else:
            body["max_tokens"] = max_tokens
            body["chat_template_kwargs"] = {"enable_thinking": False}

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            reasoning_delta = delta.get("reasoning") or ""
                            content_delta = delta.get("content") or ""
                            if reasoning_delta:
                                yield ("reasoning", reasoning_delta)
                            if content_delta:
                                yield ("content", content_delta)
                        except (KeyError, IndexError, _json.JSONDecodeError):
                            continue
        except Exception:
            logger.error("LLM 流式生成失败", exc_info=True)
            raise

    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        """向后兼容：单条 prompt 生成。"""
        resp = await self.chat([{"role": "user", "content": prompt}], max_tokens)
        return resp.content


class NoLLM:
    """空 LLM — 当未配置 LLM 时使用。"""

    async def chat(self, messages: list[Message], max_tokens: int = 2000,
                   deep_think: bool = False) -> LLMResponse:
        return LLMResponse()

    async def chat_stream(self, messages: list[Message], max_tokens: int = 2000,
                          temperature: float = 0.3, deep_think: bool = False):
        return
        yield  # noqa: make it an async generator

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
