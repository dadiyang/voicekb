"""RAG 引擎 — 基于录音内容的检索增强生成，支持多轮对话。"""

import logging

from jinja2 import Template

from voicekb.knowledge.llm import LLMBackend, Message
from voicekb.knowledge.search import SearchEngine
from voicekb.models import Recording

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 VoiceKB 智能助手，帮助用户理解和检索他们的录音内容。

你的能力：
1. 回答关于录音内容的问题（谁说了什么、讨论了哪些话题）
2. 日常闲聊和打招呼
3. 解释录音摘要和说话人信息

行为规则：
- 如果用户在打招呼或闲聊，正常友好地回应，不要去搜索录音
- 如果用户问的是录音相关的内容，会在消息中附带搜索到的相关片段，请基于这些片段回答
- 引用具体的说话人名字和内容，不要编造录音中没有的信息
- 如果录音中没有相关信息，诚实说明，可以建议用户换个关键词试试
- 用简洁清晰的中文回答"""

SUMMARY_TEMPLATE = Template("""请根据以下会议录音的转写内容，生成一份简洁的会议纪要。

## 录音信息
- 文件: {{ filename }}
- 时长: {{ duration_min }} 分钟
- 参与者: {{ speakers }}

## 转写内容
{% for seg in segments %}
**{{ seg.speaker_id }}** ({{ seg.start | int // 60 }}:{{ "%02d" | format(seg.start | int % 60) }}): {{ seg.text }}
{% endfor %}

## 请生成以下内容：
1. **关键话题**：讨论了哪些主要议题
2. **决策要点**：达成了哪些结论或决定
3. **行动项**：需要跟进的事项及负责人
4. **下一步**：后续计划

请用简洁清晰的中文回答，直接给出纪要内容，不要重复转写原文。""")

# 判断是否需要检索的简单关键词
_GREETING_KEYWORDS = {"你好", "hello", "hi", "嗨", "早上好", "下午好", "晚上好", "谢谢", "感谢", "再见", "好的", "嗯"}


def _is_casual_chat(question: str) -> bool:
    """判断是闲聊还是知识查询。"""
    q = question.strip().lower()
    # 太短且是常见招呼语
    if len(q) <= 6 and any(kw in q for kw in _GREETING_KEYWORDS):
        return True
    # 纯问候
    if q in _GREETING_KEYWORDS:
        return True
    return False


class RAGEngine:
    """检索增强生成引擎，支持多轮对话。"""

    def __init__(self, search: SearchEngine, llm: LLMBackend) -> None:
        self._search = search
        self._llm = llm

    async def answer(self, question: str,
                     history: list[Message] | None = None) -> dict:
        """基于知识库回答问题，支持多轮对话上下文。"""

        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 加入历史对话（最近 10 轮）
        if history:
            messages.extend(history[-20:])  # 最多 20 条（10轮）

        # 判断是否需要检索
        sources = []
        if _is_casual_chat(question):
            # 闲聊，不检索，直接对话
            messages.append({"role": "user", "content": question})
        else:
            # 知识查询，检索相关片段
            results = self._search.hybrid_search(question, limit=8)
            sources = [r.model_dump() for r in results[:5]]

            if results:
                context = "\n\n".join(
                    f"【{r.recording_filename} - {r.segment.speaker_id}】{r.segment.text}"
                    for r in results
                )
                user_msg = f"用户问题：{question}\n\n以下是从录音中检索到的相关内容：\n{context}"
            else:
                user_msg = f"用户问题：{question}\n\n（未从录音中找到直接相关的内容，请基于你的理解回答，并告知用户可以换个关键词试试）"

            messages.append({"role": "user", "content": user_msg})

        answer = await self._llm.chat(messages)

        if not answer:
            if _is_casual_chat(question):
                answer = "你好！我是 VoiceKB 智能助手，可以帮你查找和分析录音内容。有什么需要帮忙的吗？"
            elif sources:
                answer = "**相关录音片段：**\n\n"
                for s in sources:
                    seg = s.get("segment", {})
                    answer += f"- **{seg.get('speaker_id', '')}**: {seg.get('text', '')}\n"
                answer += "\n（LLM 暂时不可用，显示原始搜索结果）"
            else:
                answer = "未找到与您问题相关的录音内容，请尝试换个关键词。"

        return {"answer": answer, "sources": sources}

    async def classify_recording(self, recording: Recording,
                                 existing_categories: list[str]) -> str:
        """根据录音内容自动分类。"""
        if not recording.segments:
            return "其他"

        sample = "\n".join(
            f"{s.speaker_id}: {s.text}" for s in recording.segments[:25]
        )

        cats_list = ", ".join(existing_categories) if existing_categories else "工作会议, 项目讨论, 技术评审, 日常聊天, 电话沟通, 培训讲座, 面试"

        prompt = (
            f"以下是一段录音的对话内容：\n\n{sample}\n\n"
            f"可选类别：{cats_list}\n"
            "请从上述类别中选择最匹配的一个。如果都不合适，可以用2-4个字建议新类别。\n"
            "要求：只输出类别名称，不要解释。"
        )
        category = await self._llm.generate(prompt, max_tokens=20)
        category = category.strip().strip("\"'《》「」·").strip()
        if not category or len(category) > 10:
            return "其他"
        return category

    async def generate_title(self, recording: Recording) -> str:
        """根据录音内容生成简短可读的标题。"""
        if not recording.segments:
            return recording.filename

        # 取前 20 段内容让 LLM 起标题
        sample = "\n".join(
            f"{s.speaker_id}: {s.text}" for s in recording.segments[:20]
        )
        prompt = (
            f"以下是一段录音的前几句对话：\n\n{sample}\n\n"
            "请用一个简短的中文标题概括这段录音的主题，"
            "要求：不超过15个字，不加书名号，直接输出标题文字。"
        )
        title = await self._llm.generate(prompt, max_tokens=30)
        title = title.strip().strip("\"'《》「」").strip()
        if not title or len(title) > 30:
            return recording.filename
        return title

    async def summarize_recording(self, recording: Recording) -> str:
        """生成录音摘要。"""
        if not recording.segments:
            return ""

        prompt = SUMMARY_TEMPLATE.render(
            filename=recording.filename,
            duration_min=f"{recording.duration / 60:.0f}",
            speakers=", ".join(recording.speakers),
            segments=recording.segments[:100],
        )

        summary = await self._llm.generate(prompt, max_tokens=1500)

        if not summary:
            speaker_counts: dict[str, int] = {}
            for seg in recording.segments:
                speaker_counts[seg.speaker_id] = speaker_counts.get(seg.speaker_id, 0) + 1

            summary = f"## 基础信息\n\n"
            summary += f"- 时长: {recording.duration / 60:.0f} 分钟\n"
            summary += f"- 参与者: {', '.join(recording.speakers)}\n"
            summary += f"- 总计 {len(recording.segments)} 段对话\n\n"
            summary += "## 发言统计\n\n"
            for spk, count in sorted(speaker_counts.items()):
                summary += f"- {spk}: {count} 段发言\n"
            summary += "\n（LLM 未配置，仅显示基础统计）"

        return summary
