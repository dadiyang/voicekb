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
    ThinkingPart,
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

搜索策略：
- 搜索词用空格分隔的关键词，不要用自然语言句子。提取用户问题中最核心的人名、主题词、动作词
- 首次搜索优先用最核心的1-3个词，搜不到再扩展
- 如果上下文已有答案，不需要重复搜索
- 最多重试2次，每次换不同角度的关键词

回答规则：
- 引用具体说话人名字和原话，不编造
- 搜索无结果时诚实说明
- 简洁清晰的中文
- 思考过程也用中文"""


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
        """搜索录音库。query 应为2-5个关键词（如"陈总 赵工 建议"），不要用完整句子。支持人名、话题、关键词搜索。"""
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

        from pydantic_ai.usage import UsageLimits

        async with agent.iter(
            question,
            model_settings=model_settings,
            message_history=message_history or None,
            usage_limits=UsageLimits(request_limit=20),  # 最多 10 轮 tool call
        ) as run:
            async for node in run:
                if isinstance(node, CallToolsNode) and hasattr(node, "model_response"):
                    resp: ModelResponse | None = node.model_response
                    if resp is None:
                        continue
                    for part in resp.parts:
                        if isinstance(part, ThinkingPart) and part.content:
                            # vLLM reasoning-parser 解析出的思考过程
                            full_reasoning += part.content
                            yield SSEEvent("reasoning", json.dumps(part.content, ensure_ascii=False))

                        elif isinstance(part, TextPart) and part.content:
                            # 实际回答内容（reasoning-parser 已分离，无 <think> 标签）
                            full_content += part.content
                            yield SSEEvent("content", json.dumps(part.content, ensure_ascii=False))

                        elif isinstance(part, ToolCallPart):
                            tool_display = _tool_display_name(part.tool_name)
                            args = json.loads(part.args) if isinstance(part.args, str) else part.args
                            yield SSEEvent("tool_start", json.dumps({
                                "name": tool_display,
                                "args": args,
                                "tool_call_id": part.tool_call_id,
                            }, ensure_ascii=False))

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
