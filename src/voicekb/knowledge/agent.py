"""PydanticAI Agent — 替代手写 RAG，自动管理 tool calling 和多轮对话。"""

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai._agent_graph import CallToolsNode, ModelRequestNode
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from voicekb.config import Settings
from voicekb.knowledge.search import SearchEngine

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 VoiceKB 智能助手，帮助用户理解和检索他们的录音内容。

你的能力：
1. 搜索录音内容（谁说了什么、讨论了哪些话题）
2. 日常闲聊和打招呼
3. 解释录音摘要和说话人信息

行为规则：
- 需要查找录音内容时，使用 search_recordings 工具搜索
- 多轮对话时，将上下文信息融入搜索词（如用户说"具体是哪三个"，搜索时带上之前的主题）
- 引用具体的说话人名字和内容，不要编造录音中没有的信息
- 如果搜索无结果，诚实说明，建议换关键词
- 用简洁清晰的中文回答
- 思考过程也必须使用中文"""


@dataclass
class SSEEvent:
    """SSE 事件，前端按 event type 分发渲染。"""
    event: str  # request_id / tool_start / tool_end / reasoning / content / done / error
    data: str   # JSON string


def create_agent(settings: Settings, search: SearchEngine | None = None) -> Agent:
    """创建 PydanticAI Agent。可传入已有的 SearchEngine 复用连接。"""
    if search is None:
        search = SearchEngine(settings)

    model = OpenAIChatModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        ),
    )

    # 闭包变量：最近一次搜索的结构化结果（用于 sources 事件）
    last_search_sources: list[dict] = []

    agent = Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool_plain
    def search_recordings(query: str) -> str:
        """搜索录音内容。输入关键词或语义查询，返回匹配的录音片段。多轮对话时，将上下文信息融入查询词中。"""
        results = search.hybrid_search(query, limit=5)
        last_search_sources.clear()
        last_search_sources.extend(r.model_dump() for r in results[:5])
        if not results:
            return "未找到相关录音内容。建议换个关键词试试。"
        lines = []
        for r in results:
            title = r.recording_title or r.recording_filename
            lines.append(
                f"【{title} - {r.segment.speaker_id}】{r.segment.text}"
            )
        return "\n\n".join(lines)

    # 暴露 last_search_sources 供 stream_agent_response 使用
    agent._last_search_sources = last_search_sources  # type: ignore[attr-defined]

    return agent


async def stream_agent_response(
    agent: Agent,
    question: str,
    history: list[dict] | None = None,
    deep_think: bool = False,
) -> AsyncGenerator[SSEEvent, None]:
    """流式执行 agent，yield SSE 事件。

    事件类型（前端通用渲染，不感知具体 tool）：
    - tool_start: {"name": "搜索录音内容", "args": {"query": "..."}}
    - tool_end:   {"name": "搜索录音内容", "result_summary": "找到 5 条结果"}
    - reasoning:  "思考文本片段"
    - content:    "回答文本片段"
    - done:       {"answer": "完整回答", "reasoning": "完整思考"}
    - error:      "错误信息"
    """
    try:
        model_settings = {}
        if deep_think:
            model_settings["max_tokens"] = 24000
        else:
            model_settings["max_tokens"] = 2000
            model_settings["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }

        # 将 chat db 的 history 转为 PydanticAI message_history
        message_history: list[ModelMessage] = []
        if history:
            for msg in history[-20:]:  # 最近 20 轮
                if msg["role"] == "user":
                    message_history.append(
                        ModelRequest(parts=[UserPromptPart(content=msg["content"])])
                    )
                elif msg["role"] == "assistant":
                    message_history.append(
                        ModelResponse(parts=[TextPart(content=msg["content"])])
                    )

        full_reasoning = ""
        full_content = ""

        # 累积 TextPart 文本的 buffer，用于跨 part 的 <think> 标签解析
        text_buffer = ""

        async with agent.iter(
            question,
            model_settings=model_settings,
            message_history=message_history or None,
        ) as run:
            async for node in run:
                if isinstance(node, CallToolsNode) and hasattr(node, "model_response"):
                    resp: ModelResponse | None = node.model_response
                    if resp is None:
                        continue
                    for part in resp.parts:
                        if isinstance(part, TextPart) and part.content:
                            text_buffer += part.content

                        elif isinstance(part, ToolCallPart):
                            tool_display = _tool_display_name(part.tool_name)
                            args = json.loads(part.args) if isinstance(part.args, str) else part.args
                            yield SSEEvent("tool_start", json.dumps({
                                "name": tool_display,
                                "args": args,
                                "tool_call_id": part.tool_call_id,
                            }, ensure_ascii=False))

                    # 每轮 CallToolsNode 结束后，统一解析累积的 text_buffer
                    if text_buffer:
                        reasoning_text, content_text = _parse_thinking(text_buffer)
                        if reasoning_text:
                            full_reasoning += reasoning_text
                            yield SSEEvent("reasoning", json.dumps(reasoning_text, ensure_ascii=False))
                        if content_text:
                            full_content += content_text
                            yield SSEEvent("content", json.dumps(content_text, ensure_ascii=False))
                        text_buffer = ""

                elif isinstance(node, ModelRequestNode) and hasattr(node, "request"):
                    req = node.request
                    if req:
                        for part in req.parts:
                            if isinstance(part, ToolReturnPart):
                                tool_display = _tool_display_name(part.tool_name)
                                content_str = str(part.content)
                                summary = _summarize_tool_result(part.tool_name, content_str)
                                yield SSEEvent("tool_end", json.dumps({
                                    "name": tool_display,
                                    "result_summary": summary,
                                    "tool_call_id": part.tool_call_id,
                                }, ensure_ascii=False))
                                # 发送 sources（来自 search_recordings 闭包）
                                sources = getattr(agent, "_last_search_sources", [])
                                if sources:
                                    yield SSEEvent("sources", json.dumps(sources, ensure_ascii=False))

        # 完成
        result = {"answer": full_content, "reasoning": full_reasoning}
        yield SSEEvent("done", json.dumps(result, ensure_ascii=False))

    except Exception as e:
        logger.error("Agent 执行失败", exc_info=True)
        yield SSEEvent("error", json.dumps("服务异常，请重试", ensure_ascii=False))


def _parse_thinking(text: str) -> tuple[str, str]:
    """从文本中分离 <think>...</think> 思考过程和实际内容。

    返回 (reasoning, content)。处理未闭合标签的情况。
    """
    import re
    # 完整的 <think>...</think>
    match = re.search(r"<think>(.*?)</think>(.*)", text, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    # 只有 <think> 没有 </think>（thinking 被截断或整段都是 thinking）
    if "<think>" in text:
        return text.replace("<think>", "").strip(), ""
    # 纯 content
    return "", text.strip()


# ── Tool 展示信息（后端定义，前端不感知） ──────────────────────────

_TOOL_DISPLAY_NAMES = {
    "search_recordings": "搜索录音内容",
}


def _tool_display_name(tool_name: str) -> str:
    return _TOOL_DISPLAY_NAMES.get(tool_name, tool_name)


def _summarize_tool_result(tool_name: str, result: str) -> str:
    """从 tool 返回值生成用户友好的摘要。"""
    if tool_name == "search_recordings":
        if "未找到" in result:
            return "未找到相关内容"
        count = result.count("【")
        return f"找到 {count} 条相关片段"
    return "执行完成"
