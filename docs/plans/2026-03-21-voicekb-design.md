# VoiceKB 设计文档

> 把日常录音变成可搜索、可对话的个人知识库。

## 背景

Get笔记录音卡提供了便捷的全天候录音能力，但自带的转写和总结功能较基础：不支持声纹识别、总结 prompt 不可自定义、无法与个人知识体系打通。

VoiceKB 解决的核心问题：**录音 → 结构化知识 → AI 可查询**。

## 整体架构

四层架构，每层独立可替换：

```
┌──────────────────────────────────────────────────┐
│                  消费层 (Consume)                  │
│  MCP Server ← CC/小龙虾    REST API    uni-app    │
├──────────────────────────────────────────────────┤
│                  知识层 (Knowledge)                │
│  全文搜索(FTS5)  向量搜索(ChromaDB)  LLM总结/RAG  │
├──────────────────────────────────────────────────┤
│                  处理层 (Process)                  │
│  WhisperX(ASR+声纹+对齐)  声纹库管理  结构化输出    │
├──────────────────────────────────────────────────┤
│                  获取层 (Ingest)                   │
│  Get笔记适配器    本地文件导入    扩展适配器         │
└──────────────────────────────────────────────────┘
                        │
                  SQLite + Markdown
                  (持久化 & 可读存储)
```

### 架构设计原则

参考 smart_trade 项目的实践：
- **面向对象 + 抽象封装**：每层通过 Protocol/ABC 定义接口，实现可替换
- **模块化**：每个组件独立可测试、可替换
- **适配器模式**：数据源、LLM、存储后端都通过适配器接入

## 获取层 (Ingest)

### 适配器接口

```python
class IngestAdapter(Protocol):
    """数据源适配器协议"""
    async def list_new(self, since: datetime) -> list[AudioMeta]: ...
    async def download(self, meta: AudioMeta, dest: Path) -> Path: ...
```

### Get笔记适配器

Get笔记无公开 API，通过 Playwright 浏览器自动化从 biji.com 获取：

1. Cookie 持久化登录
2. 增量同步（记录上次同步时间戳，只拉新录音）
3. 下载音频文件 + 保留 Get笔记原始转写文本作为 baseline
4. 按音频文件 hash 去重

### 本地文件适配器

监听指定目录，新增 mp3/wav/m4a/flac 文件自动进入处理管道。

## 处理层 (Process)

### ASR + 声纹分离

核心引擎：[WhisperX](https://github.com/m-bain/whisperX)（Whisper large-v3 + pyannote 4.0）

```
音频 → WhisperX → segments[{start, end, text, speaker}]
```

- ASR 模型：Whisper large-v3，中文效果好
- 声纹分离：pyannote speaker-diarization-community-1（当前最强开源模型）
- 自动检测说话人数量

### 声纹库（渐进式）

| 版本 | 能力 |
|------|------|
| V1 | 单次录音内区分说话人（Speaker_01/02） |
| V2 | 跨录音识别同一人（pyannote embedding 余弦匹配） |
| V3 | 用户标注姓名 → 更新声纹库 → 自动识别 |

### 低质量音频对策

- Whisper 对 ASR 鲁棒性好，低质量音频问题不大
- 声纹分离在噪声环境下精度下降，通过预处理降噪 + 置信度阈值缓解
- 后期可用少量领域数据微调提升

### 输出格式

每条录音生成 JSON（程序消费）+ Markdown（人可读）：

JSON:
```json
{
  "id": "rec_20260321_143000",
  "source": "getbiji",
  "duration": 1800,
  "speakers": ["张三", "SPEAKER_02"],
  "segments": [
    {"start": 0.5, "end": 3.2, "text": "我觉得这个方案可以", "speaker": "张三"}
  ],
  "metadata": {"场景": "周会", "标签": ["产品讨论"]}
}
```

Markdown:
```markdown
# 2026-03-21 14:30 录音
- 来源: Get笔记 | 时长: 30分钟
- 参与者: 张三, Speaker_02

## 对话记录
**张三** (00:00:30): 我觉得这个方案可以...
**Speaker_02** (00:00:45): 但是有个问题...
```

## 知识层 (Knowledge)

### 搜索（V1 核心）

双引擎搜索：

- **关键词搜索**：SQLite FTS5 全文索引
- **语义搜索**：bge-large-zh-v1.5 embedding → ChromaDB 向量检索
- 检索粒度：同一说话人的连续发言合并为一个 chunk
- 结果合并排序，返回 top-K + 原始上下文

### LLM 总结/问答（V1 核心）

**自动总结**：录音处理完成后，按模板自动生成摘要。

Prompt 模板系统：用户在 `templates/` 目录下放 Jinja2 模板，按录音标签自动匹配：
- 会议纪要模板：决策、行动项、负责人
- 日常对话模板：关键话题、有趣观点、待跟进
- 自由模板：用户自定义

**RAG 问答**：检索相关 segments → 注入 context → LLM 回答。

LLM 可插拔：通过配置切换本地模型或 API。

### 知识图谱（V2 后期）

- 人物关系网络
- 话题跨录音演进脉络
- 时间线视图

V1 不实现，但数据模型预留扩展点。

## 消费层 (Consume)

### MCP Server

CC/小龙虾通过 MCP 协议直接查询知识库：

- `search_recordings(query, speaker?, date_range?)` — 搜索录音内容
- `get_recording_summary(recording_id)` — 某次录音摘要
- `ask_knowledge(question)` — 基于全量知识库的 RAG 问答
- `list_recent(days=7)` — 最近录音列表
- `get_speaker_history(speaker_name, topic?)` — 某人说过的话

### REST API

FastAPI 实现，与 MCP 工具一一对应，供 Web UI 和其他系统调用。

### 前端（uni-app）

复用 hotel-shop 项目沉淀的 uni-app + 小程序 UI 体系和开发经验：

- 录音列表 + 播放器（点击文字跳转对应音频位置）
- 搜索界面
- 说话人标注（给 Speaker_01 标记真名）
- 录音标签管理
- 总结模板管理
- 支持 H5 + 小程序双端

## 技术栈

| 层 | 技术选择 | 理由 |
|---|---|---|
| 获取 | Playwright | Get笔记无 API，浏览器自动化最可靠 |
| ASR + 声纹 | WhisperX (large-v3 + pyannote community-1) | 一站式，star 15k+，中文好 |
| 存储 | SQLite + Markdown | 轻量、Git 可追踪、自托管友好 |
| 向量搜索 | ChromaDB + bge-large-zh-v1.5 | 本地运行、中文优化 |
| LLM | 可插拔（配置切换） | 灵活适配 |
| 后端 API | FastAPI + MCP SDK | Python 生态一致 |
| 前端 | uni-app (Vue3) | 复用 hotel-shop 经验，H5 + 小程序双端 |

## 开源信息

- 协议：MIT
- 语言：Python（后端）+ Vue3/uni-app（前端）
- 最低要求：GPU 服务器（ASR + 声纹本地处理）

## 交付阶段

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| V1 | 本地文件 → ASR + 声纹 → Markdown + 搜索 + MCP | 可用的 CLI + API + MCP |
| V1.5 | Get笔记适配器 + Web UI | 完整的数据获取 + 可视化 |
| V2 | 声纹库跨录音识别 + 知识图谱 + 小程序端 | 完整的个人知识库 |
