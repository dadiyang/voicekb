"""RAG 引擎 — 基于录音内容的检索增强生成，支持多轮对话。"""

import json
import logging

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

# ── 平台默认 prompt（代码内维护，升级自动更新） ──────────────────────────
# 用户自定义存 DB 覆盖默认，重置=删 DB 记录回到这里

BUILTIN_PROMPTS: dict[str, str] = {
    "_default": (
        "你是专业的录音分析助手。请根据以下对话内容生成结构化总结。\n\n"
        "要求：\n"
        "1. **主题概述**：一句话说明这段录音在讨论什么\n"
        "2. **关键要点**：按重要程度列出核心观点和信息（不超过5条）\n"
        "3. **涉及人物**：每个说话人的主要立场或贡献\n\n"
        "规则：只基于实际内容总结，不要编造或推测。用简洁清晰的中文输出。"
    ),
    "工作会议": (
        "你是资深会议纪要撰写者。请将以下会议录音转写为专业的会议纪要。\n\n"
        "输出格式：\n"
        "1. **会议主题**：一句话概括\n"
        "2. **关键决策**：明确列出达成的每项决定，附带具体数字/方案\n"
        "3. **行动项**：表格形式——任务 | 负责人 | 截止时间（如有）\n"
        "4. **待确认事项**：讨论了但未达成结论的议题\n"
        "5. **下次会议**：后续安排（如有提及）\n\n"
        "规则：决策必须引用原话中的具体数字和方案，不要用模糊措辞。"
    ),
    "项目讨论": (
        "请提取以下项目讨论录音的核心信息。\n\n"
        "输出格式：\n"
        "1. **项目状态**：当前进展总结\n"
        "2. **讨论要点**：每个议题一段，说明问题、各方观点、结论\n"
        "3. **风险与阻塞**：提到的风险、困难或阻塞项\n"
        "4. **行动项**：任务 | 负责人\n"
        "5. **里程碑**：提到的时间节点和交付物\n\n"
        "规则：保留具体的技术细节和数据，不要过度概括。"
    ),
    "技术评审": (
        "请将以下技术评审讨论整理为评审报告。\n\n"
        "输出格式：\n"
        "1. **方案概述**：被评审的技术方案一句话说明\n"
        "2. **评审意见**：按说话人分别列出提出的问题和建议\n"
        "3. **结论**：方案是否通过，需要哪些修改\n"
        "4. **遗留问题**：需要进一步调研或验证的点\n"
        "5. **跟进事项**：谁负责什么修改，什么时候完成\n\n"
        "规则：技术细节要准确保留，评审意见要归因到具体说话人。"
    ),
    "面试": (
        "请根据以下面试录音生成面试记录。\n\n"
        "输出格式：\n"
        "1. **候选人表现**：整体印象和沟通能力\n"
        "2. **关键问答**：列出面试中的重要问题及候选人回答要点\n"
        "3. **技能评估**：候选人展示出的技能和经验\n"
        "4. **关注点**：面试官提出的顾虑或追问方向\n\n"
        "规则：客观记录，不做录用建议。保护候选人隐私，不输出敏感信息。"
    ),
    "日常聊天": (
        "请简要整理以下对话的内容。\n\n"
        "输出格式：\n"
        "1. **聊了什么**：用2-3句话概括对话主题\n"
        "2. **有趣观点**：值得记住的想法或信息\n"
        "3. **待办事项**：如果对话中提到了要做的事情，列出来\n\n"
        "规则：轻松的语气，不需要太正式。"
    ),
    "电话沟通": (
        "请整理以下电话录音的关键内容。\n\n"
        "输出格式：\n"
        "1. **通话目的**：为什么打这个电话\n"
        "2. **沟通结果**：达成了什么共识或结论\n"
        "3. **后续行动**：双方各自需要跟进的事项\n\n"
        "规则：简明扼要，突出结果和行动项。"
    ),
    "培训讲座": (
        "请提取以下培训/讲座录音的知识要点。\n\n"
        "输出格式：\n"
        "1. **主题**：讲座的核心主题\n"
        "2. **知识要点**：按逻辑顺序列出关键知识点\n"
        "3. **实操建议**：讲者给出的具体建议或方法论\n"
        "4. **参考资源**：提到的工具、书籍、链接等\n\n"
        "规则：保留具体的方法论和数据，便于回顾学习。"
    ),
}

def get_builtin_prompt(category: str) -> str:
    """获取平台内置的默认 prompt。"""
    return BUILTIN_PROMPTS.get(category, BUILTIN_PROMPTS["_default"])

_GREETING_KEYWORDS = {"你好", "hello", "hi", "嗨", "早上好", "下午好", "晚上好", "谢谢", "感谢", "再见", "好的", "嗯"}


def _is_casual_chat(question: str) -> bool:
    q = question.strip().lower()
    if len(q) <= 6 and any(kw in q for kw in _GREETING_KEYWORDS):
        return True
    return q in _GREETING_KEYWORDS


class RAGEngine:
    """检索增强生成引擎，支持多轮对话。"""

    def __init__(self, search: SearchEngine, llm: LLMBackend) -> None:
        self._search = search
        self._llm = llm

    async def answer(self, question: str,
                     history: list[Message] | None = None) -> dict:
        """基于知识库回答问题，支持多轮对话上下文。"""
        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            messages.extend(history[-20:])

        sources = []
        if _is_casual_chat(question):
            messages.append({"role": "user", "content": question})
        else:
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

    # ── 合并调用：标题 + 分类（1 次 LLM） ────────────────────────────────

    async def classify_and_title(self, recording: Recording,
                                 existing_categories: list[str]) -> tuple[str, str]:
        """一次 LLM 调用同时生成标题和分类。返回 (title, category)。"""
        if not recording.segments:
            return recording.filename, "其他"

        sample = "\n".join(
            f"{s.speaker_id}: {s.text}" for s in recording.segments[:25]
        )
        cats_list = ", ".join(existing_categories) if existing_categories else "工作会议, 项目讨论, 技术评审, 日常聊天, 电话沟通, 培训讲座, 面试"

        prompt = (
            f"以下是一段录音的对话内容：\n\n{sample}\n\n"
            f"请完成两个任务，以 JSON 格式输出：\n"
            f"1. title: 用一个简短的中文标题概括主题（不超过15个字）\n"
            f"2. category: 从以下类别中选最匹配的一个：{cats_list}\n\n"
            f'直接输出 JSON：{{"title": "...", "category": "..."}}\n/no_think'
        )

        raw = await self._llm.generate(prompt, max_tokens=100)
        raw = raw.strip()

        # 解析 JSON
        title = recording.filename
        category = "其他"
        try:
            # 尝试提取 JSON（可能被包裹在 markdown code block 中）
            if "```" in raw:
                raw = raw.split("```")[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            data = json.loads(raw)
            title = data.get("title", "").strip().strip("\"'《》「」") or recording.filename
            category = data.get("category", "").strip().strip("\"'") or "其他"
            if len(title) > 30:
                title = recording.filename
            if len(category) > 10:
                category = "其他"
        except (json.JSONDecodeError, AttributeError):
            logger.warning("标题+分类 JSON 解析失败: %s", raw[:100])

        return title, category

    # ── 摘要生成（支持自定义 prompt） ───────────────────────────────────

    async def summarize_recording(self, recording: Recording,
                                  custom_prompt: str | None = None) -> str:
        """生成录音摘要。custom_prompt 是用户自定义的摘要指令。"""
        if not recording.segments:
            return ""

        # 转写内容（始终附加，用户不需要管）
        transcript = "\n".join(
            f"**{s.speaker_id}** ({int(s.start)//60}:{int(s.start)%60:02d}): {s.text}"
            for s in recording.segments[:100]
        )

        # 优先级：用户自定义 > 平台内置按分类 > 平台通用默认
        instruction = custom_prompt or get_builtin_prompt(recording.category)

        # 替换友好占位符
        instruction = instruction.replace("{标题}", recording.title or recording.filename)
        instruction = instruction.replace("{参与者}", ", ".join(recording.speakers))
        instruction = instruction.replace("{时长}", f"{recording.duration / 60:.0f}")
        instruction = instruction.replace("{分类}", recording.category)

        # 录音信息头 + 指令 + 转写内容
        header = f"录音：{recording.title or recording.filename}，时长 {recording.duration/60:.0f} 分钟，参与者：{', '.join(recording.speakers)}"
        prompt = f"{header}\n\n{instruction}\n\n## 转写内容\n{transcript}"

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
