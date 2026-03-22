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
| **语音识别** | 基于 faster-whisper，中文准确率高，GPU 加速 30 分钟录音 < 5 分钟处理完 |
| **说话人分离** | 自动区分每个人说了什么，跨录音识别同一人（声纹关联） |
| **智能摘要** | LLM 自动生成会议纪要，支持按分类自定义总结模板 |
| **双引擎搜索** | 关键词精确匹配 + 语义向量搜索，快速定位内容 |
| **AI 问答** | 直接问录音内容，多轮对话，引用原文出处 |
| **双版本转写** | 原始 ASR 输出 + LLM 润色的流畅版，一键切换 |

## 技术亮点

- **声纹跨录音关联** — 不只是单次录音内区分说话人，而是跨所有录音识别同一人。标注一次"张三"，所有录音中张三自动识别
- **三层 Prompt 体系** — 平台默认 → 分类自定义 → 单条录音专属，总结方式层层可调
- **总结 + 润色并行** — asyncio.gather 同时执行 LLM 摘要和文本润色，处理时间减半
- **完全本地部署** — ASR、声纹、向量搜索、LLM 全部本地运行，录音数据不出你的服务器

## 架构

```
┌─────────────────────────────────────────────┐
│  消费层   uni-app H5 / 小程序 / REST API     │
├─────────────────────────────────────────────┤
│  知识层   SQLite FTS5 + ChromaDB + LLM RAG   │
├─────────────────────────────────────────────┤
│  处理层   faster-whisper + pyannote.audio + wespeaker│
├─────────────────────────────────────────────┤
│  存储层   SQLite + Markdown 双写              │
└─────────────────────────────────────────────┘
```

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
VOICEKB_WHISPER_DEVICE=cuda
VOICEKB_LLM_BASE_URL=http://localhost:18090/v1
VOICEKB_LLM_MODEL=Qwen/Qwen3-8B
VOICEKB_LLM_API_KEY=not-needed
```

本地 LLM 推荐用 [vLLM](https://github.com/vllm-project/vllm) 或 [Ollama](https://ollama.ai) 部署 Qwen3-8B。

### 模式 B：无 GPU — CPU + 云端 LLM

ASR 和声纹在 CPU 上运行（较慢但可用），LLM 对接云端 API。

```bash
# .env
VOICEKB_WHISPER_DEVICE=cpu
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
| `WHISPER_MODEL` | `small` | Whisper 模型（`small` / `medium` / `large-v3`） |
| `WHISPER_DEVICE` | `cuda` | 运行设备（`cuda` / `cpu`） |
| `LLM_BACKEND` | `openai_compatible` | LLM 后端（`openai_compatible` / `none`） |
| `LLM_BASE_URL` | `http://localhost:8000/v1` | LLM API 地址 |
| `LLM_MODEL` | `Qwen/Qwen3-8B` | 模型名称 |
| `LLM_API_KEY` | `not-needed` | API 密钥（本地部署不需要） |
| `PORT` | `8080` | 服务端口 |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | uni-app (Vue 3) — 同时编译 H5 和微信小程序 |
| 后端 | FastAPI + SQLite + ChromaDB |
| ASR | faster-whisper (CTranslate2 加速) |
| 声纹 | pyannote.audio 3.1 (神经网络分割 + wespeaker embedding) |
| 向量搜索 | ChromaDB + bge-small-zh-v1.5 |
| LLM | 可插拔 — 本地 Qwen3-8B 或任意 OpenAI 兼容 API |

## License

[Apache-2.0](LICENSE)

[English](README.md)
