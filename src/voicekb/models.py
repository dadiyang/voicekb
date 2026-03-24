"""数据模型 — 跨层共享的 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """一段带说话人标签的转写文本。"""

    start: float
    end: float
    text: str
    text_polished: str = ""  # LLM 润色后的流畅版（空=未润色）
    speaker_id: str  # "SPEAKER_00" 或注册后的真名
    confidence: float = 1.0


class Recording(BaseModel):
    """一条录音记录。"""

    id: str
    filename: str
    title: str = ""  # LLM 生成的可读标题，空则显示 filename
    source: str = "upload"
    duration: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = "pending"  # pending | processing | completed | failed
    segments: list[Segment] = []
    speakers: list[str] = []
    summary: str = ""
    category: str = ""  # LLM 自动分类，用户可修改
    custom_prompt: str = ""  # 录音级自定义摘要 prompt（覆盖分类级）
    tags: list[str] = []
    error: str | None = None


class Speaker(BaseModel):
    """已注册的说话人。"""

    id: str
    name: str
    embedding: list[float]
    recording_ids: list[str] = []
    created_at: datetime = Field(default_factory=datetime.now)


class SearchResult(BaseModel):
    """搜索结果条目。"""

    recording_id: str
    recording_filename: str
    recording_title: str = ""
    segment: Segment
    score: float
    context: list[Segment] = []
