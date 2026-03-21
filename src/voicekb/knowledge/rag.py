"""RAG 引擎 — 基于录音内容的检索增强生成。"""

import logging

from jinja2 import Template

from voicekb.knowledge.llm import LLMBackend
from voicekb.knowledge.search import SearchEngine
from voicekb.models import Recording

logger = logging.getLogger(__name__)

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


RAG_TEMPLATE = Template("""你是一个基于录音知识库的智能助手。请根据以下录音内容回答用户的问题。

## 相关录音片段
{% for result in results %}
### {{ result.recording_filename }} — {{ result.segment.speaker_id }}
> {{ result.segment.text }}
{% endfor %}

## 用户问题
{{ question }}

## 要求
- 基于上述录音内容回答，引用具体的说话人和内容
- 如果录音中没有相关信息，诚实说明
- 用简洁清晰的中文回答""")


class RAGEngine:
    """检索增强生成引擎。"""

    def __init__(self, search: SearchEngine, llm: LLMBackend) -> None:
        self._search = search
        self._llm = llm

    async def answer(self, question: str) -> dict:
        """基于知识库回答问题。"""
        # 检索相关片段
        results = self._search.hybrid_search(question, limit=10)

        if not results:
            return {
                "answer": "未找到与您问题相关的录音内容。",
                "sources": [],
            }

        # 生成 RAG prompt
        prompt = RAG_TEMPLATE.render(results=results, question=question)

        answer = await self._llm.generate(prompt)

        if not answer:
            # LLM 不可用时，返回搜索结果摘要
            answer = "**相关录音片段：**\n\n"
            for r in results[:5]:
                answer += f"- **{r.segment.speaker_id}**: {r.segment.text}\n"
            answer += "\n（LLM 未配置，显示原始搜索结果）"

        return {
            "answer": answer,
            "sources": [r.model_dump() for r in results[:5]],
        }

    async def summarize_recording(self, recording: Recording) -> str:
        """生成录音摘要。"""
        if not recording.segments:
            return ""

        prompt = SUMMARY_TEMPLATE.render(
            filename=recording.filename,
            duration_min=f"{recording.duration / 60:.0f}",
            speakers=", ".join(recording.speakers),
            segments=recording.segments[:100],  # 限制长度
        )

        summary = await self._llm.generate(prompt, max_tokens=1500)

        if not summary:
            # LLM 不可用时，生成基础摘要
            speaker_counts = {}
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
