<h1 align="center">
  <br>
  VoiceKB
  <br>
</h1>

<h4 align="center">把日常录音变成可搜索、可对话的个人知识库</h4>

<p align="center">
  <img src="https://img.shields.io/badge/部署-完全本地-success?style=flat-square" alt="本地部署">
  <img src="https://img.shields.io/badge/隐私-数据不出服务器-blue?style=flat-square" alt="隐私安全">
  <img src="https://img.shields.io/badge/平台-H5%20%2B%20小程序-blueviolet?style=flat-square" alt="跨平台">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square" alt="Apache-2.0">
</p>

<p align="center">
  <img src="docs/images/home.png" width="180" alt="录音列表">
  <img src="docs/images/detail.png" width="180" alt="录音详情">
  <img src="docs/images/search.png" width="180" alt="全文搜索">
  <img src="docs/images/chat.png" width="180" alt="AI问答">
</p>

---

## 它能做什么

上传一段录音，VoiceKB 自动完成：

| 能力 | 说明 |
|------|------|
| **语音识别** | Whisper ASR，中文准确率高，GPU 加速 30 分钟录音约 1 分钟处理完 |
| **说话人分离** | 自动区分每个人说了什么，跨录音识别同一人（声纹关联） |
| **智能摘要** | LLM 自动生成会议纪要，支持按分类自定义总结模板 |
| **双引擎搜索** | 关键词精确匹配 + 语义向量搜索，快速定位内容 |
| **AI Agent 问答** | PydanticAI Agent + tool calling，自动搜索录音，多轮对话，引用来源，深度思考模式 |
| **双版本转写** | 原始 ASR 输出 + LLM 润色的流畅版，一键切换 |

## 技术亮点

- **声纹跨录音关联** — 不只是单次录音内区分说话人，而是跨所有录音识别同一人。标注一次"张三"，所有录音中张三自动识别
- **三层 Prompt 体系** — 平台默认 → 分类自定义 → 单条录音专属，总结方式层层可调
- **总结 + 润色并行** — asyncio.gather 同时执行 LLM 摘要和文本润色，处理时间减半
- **可插拔 AI 后端** — ASR 和 LLM 统一 OpenAI 兼容 API，改个 URL 就能切换本地/云端，零代码改动
- **完全本地部署** — ASR、声纹、向量搜索、LLM 可全部本地运行，录音数据不出你的服务器

## 架构

```
┌──────────────────────────────────────────────────────┐
│  消费层     uni-app H5 / 小程序 / REST API           │
├──────────────────────────────────────────────────────┤
│  知识层     PydanticAI Agent + ChromaDB + FTS5       │
├──────────────────────────────────────────────────────┤
│  处理层     ASR (HTTP API) + resemblyzer + 谱聚类    │
├──────────────────────────────────────────────────────┤
│  存储层     SQLite + Markdown 双写                   │
└──────────────┬───────────────────┬───────────────────┘
               │  OpenAI 兼容 API  │
    ┌──────────┴──┐     ┌──────────┴──────────┐
    │  ASR 服务   │     │    LLM 服务          │
    │ (本地/云端)  │     │   (本地/云端)         │
    └─────────────┘     └─────────────────────┘
```

> VoiceKB 本身**不绑定任何 AI 模型**，所有智能通过标准 HTTP API 调用——改个 URL 即可切换后端。

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+（构建前端）
- 8GB+ RAM
- GPU 可选（有 GPU 处理快 10 倍，无 GPU 也能跑）

### 1. 后端

```bash
git clone https://github.com/dadiyang/voicekb.git
cd voicekb
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 按需修改
```

### 2. 前端

```bash
cd client
npm install
npx uni build -p h5
cd ..
```

构建产物在 `client/dist/build/h5/`，后端会自动加载。

### 3. 启动

```bash
PYTHONPATH=src python -m uvicorn voicekb.api.app:app --host 0.0.0.0 --port 8080
```

手机浏览器访问 `http://<服务器IP>:8080`，开始使用。

## 部署模式

VoiceKB 支持两种部署方式，按你的硬件条件选择：

### 模式 A：有 GPU — 全部本地（推荐）

所有计算在本地完成，数据零外传。需要 NVIDIA GPU（4GB+ VRAM）。

```bash
# .env
VOICEKB_ASR_BASE_URL=http://localhost:8000/v1
VOICEKB_ASR_MODEL=medium
VOICEKB_LLM_BASE_URL=http://localhost:18090/v1
VOICEKB_LLM_MODEL=Qwen3.5-35B-A3B
```

本地 ASR 推荐 [whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice)（Docker），本地 LLM 推荐 [llama.cpp](https://github.com/ggml-org/llama.cpp) 或 [Ollama](https://ollama.ai)。

### 模式 B：无 GPU — CPU + 云端 LLM

ASR 和声纹在 CPU 上运行（较慢但可用），LLM 对接云端 API。

```bash
# .env
VOICEKB_ASR_BASE_URL=https://api.openai.com/v1
VOICEKB_ASR_MODEL=whisper-1
VOICEKB_ASR_API_KEY=sk-your-api-key
VOICEKB_LLM_BASE_URL=https://api.deepseek.com/v1   # 或通义千问、OpenAI 等
VOICEKB_LLM_MODEL=deepseek-chat
VOICEKB_LLM_API_KEY=sk-your-api-key
```

> 任何兼容 OpenAI Chat Completions API 的服务都可以直接对接，无需改代码。

### 性能对比

| 环节 | GPU (RTX 3060+) | CPU |
|------|-----------------|-----|
| 30 分钟录音 ASR | ~3 分钟 | ~30 分钟 |
| 声纹分离 | ~10 秒 | ~30 秒 |
| LLM 摘要（本地 8B） | ~15 秒 | N/A（用云端 API ~5 秒） |

## 配置参考

通过 `.env` 文件或环境变量配置（前缀 `VOICEKB_`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ASR_BASE_URL` | `http://localhost:8000/v1` | Whisper 兼容 API 地址 |
| `ASR_MODEL` | `medium` | 模型名（`medium` / `large-v3` / `whisper-1`） |
| `ASR_API_KEY` | `not-needed` | API 密钥（云端 ASR 需要） |
| `LLM_BASE_URL` | `http://localhost:18090/v1` | LLM API 地址 |
| `LLM_MODEL` | `Qwen3.5-35B-A3B` | 模型名 |
| `LLM_API_KEY` | `not-needed` | API 密钥（云端 LLM 需要） |
| `PORT` | `18089` | 服务端口 |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | uni-app (Vue 3) — H5 + 微信小程序 |
| 后端 | FastAPI + SQLite + ChromaDB |
| AI Agent | PydanticAI — tool calling、多轮推理 |
| ASR | 任意 OpenAI Whisper 兼容 API（本地或云端） |
| 声纹 | resemblyzer (d-vector) + 谱聚类 |
| 向量搜索 | ChromaDB + bge-base-zh-v1.5 |
| LLM | 任意 OpenAI Chat 兼容 API（本地或云端） |

## License

[Apache-2.0](LICENSE)

[English](README.md)
