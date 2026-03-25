<h1 align="center">
  <br>
  VoiceKB
  <br>
</h1>

<h4 align="center">Turn everyday recordings into a searchable, conversational personal knowledge base</h4>

<p align="center"><a href="README_zh.md">中文文档</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Deploy-Fully%20Local-success?style=flat-square" alt="Fully Local">
  <img src="https://img.shields.io/badge/Privacy-Data%20Never%20Leaves%20Your%20Server-blue?style=flat-square" alt="Privacy">
  <img src="https://img.shields.io/badge/Platform-H5%20%2B%20Mini%20Program-blueviolet?style=flat-square" alt="Cross Platform">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square" alt="Apache-2.0">
</p>

<p align="center">
  <img src="docs/images/home.png" width="180" alt="Recording List">
  <img src="docs/images/detail.png" width="180" alt="Recording Detail">
  <img src="docs/images/search.png" width="180" alt="Full-text Search">
  <img src="docs/images/chat.png" width="180" alt="AI Q&A">
</p>

---

## What It Does

Upload a recording and VoiceKB handles the rest automatically:

| Capability | Description |
|------------|-------------|
| **Speech Recognition** | Whisper ASR with high Chinese accuracy — GPU processes a 30-minute recording in about 1 minute |
| **Speaker Diarization** | Automatically identifies who said what, and recognizes the same speaker across multiple recordings (voice fingerprint linking) |
| **Smart Summarization** | LLM generates meeting minutes automatically; supports per-category custom summary templates |
| **Dual-engine Search** | Exact keyword matching + semantic vector search to locate content quickly |
| **AI Agent Q&A** | PydanticAI agent with tool calling — auto-searches, multi-turn dialogue, source citations, deep think mode |
| **Dual Transcript Versions** | Raw ASR output alongside an LLM-polished fluent version, switchable with one tap |

## Key Innovations

- **Cross-recording Voice Fingerprint Linking** — Speaker identity is tracked not just within a single recording, but across your entire library. Label a speaker once, and they are recognized automatically in every recording.
- **Three-tier Prompt System** — Platform default → category-level customization → per-recording override. Every layer of summarization behavior is adjustable.
- **Summarization + Polishing in Parallel** — `asyncio.gather` runs LLM summarization and text polishing concurrently, cutting processing time in half.
- **Pluggable AI Backend** — All AI services (ASR + LLM) communicate via OpenAI-compatible APIs. Switch from local to cloud by changing a URL in `.env` — zero code changes
- **Fully Local Deployment** — ASR, voice fingerprinting, vector search, and LLM can all run on your own server. Your recordings never leave your machine

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Consumer     uni-app H5 / Mini Program / REST API   │
├──────────────────────────────────────────────────────┤
│  Knowledge    PydanticAI Agent + ChromaDB + FTS5     │
├──────────────────────────────────────────────────────┤
│  Processing   ASR (HTTP API) + resemblyzer + clustering│
├──────────────────────────────────────────────────────┤
│  Storage      SQLite + Markdown dual-write           │
└──────────────┬───────────────────┬───────────────────┘
               │ OpenAI-compatible │
    ┌──────────┴──┐     ┌──────────┴──────────┐
    │ ASR Service │     │    LLM Service       │
    │ (local/cloud)│     │  (local/cloud)       │
    └─────────────┘     └─────────────────────┘
```

> VoiceKB itself has **zero AI model dependencies**. All intelligence comes through standard HTTP APIs — swap backends without changing code.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend build)
- 8 GB+ RAM
- GPU optional (10× faster with GPU; works on CPU too)

### 1. Backend

```bash
git clone https://github.com/dadiyang/voicekb.git
cd voicekb
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit as needed
```

### 2. Frontend

```bash
cd client
npm install
npx uni build -p h5
cd ..
```

The built H5 files are in `client/dist/build/h5/` and served automatically by the backend.

### 3. Start

```bash
PYTHONPATH=src python -m uvicorn voicekb.api.app:app --host 0.0.0.0 --port 8080
```

Open `http://<server-ip>:8080` in your mobile browser to get started.

## Deployment Modes

VoiceKB supports two deployment modes — choose based on your hardware:

### Mode A: With GPU — Fully Local (Recommended)

All computation runs locally; zero data egress. Requires an NVIDIA GPU (4 GB+ VRAM).

```bash
# .env
VOICEKB_ASR_BASE_URL=http://localhost:8000/v1
VOICEKB_ASR_MODEL=medium
VOICEKB_LLM_BASE_URL=http://localhost:18090/v1
VOICEKB_LLM_MODEL=Qwen3.5-35B-A3B
```

For local ASR, we recommend [whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice) (Docker). For local LLM, we recommend [llama.cpp](https://github.com/ggml-org/llama.cpp) or [Ollama](https://ollama.ai).

### Mode B: Without GPU — CPU + Cloud LLM

ASR and speaker diarization run on CPU (slower but functional); LLM calls go to a cloud API.

```bash
# .env
VOICEKB_ASR_BASE_URL=https://api.openai.com/v1
VOICEKB_ASR_MODEL=whisper-1
VOICEKB_ASR_API_KEY=sk-your-api-key
VOICEKB_LLM_BASE_URL=https://api.deepseek.com/v1   # or Qwen, OpenAI, etc.
VOICEKB_LLM_MODEL=deepseek-chat
VOICEKB_LLM_API_KEY=sk-your-api-key
```

> Any service compatible with the OpenAI Chat Completions API works out of the box — no code changes required.

### Performance Comparison

| Stage | GPU (RTX 3060+) | CPU |
|-------|-----------------|-----|
| ASR — 30-minute recording | ~3 min | ~30 min |
| Speaker diarization | ~10 sec | ~30 sec |
| LLM summarization (local 8B) | ~15 sec | N/A (cloud API ~5 sec) |

## Configuration

Configure via `.env` file or environment variables (prefix `VOICEKB_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ASR_BASE_URL` | `http://localhost:8000/v1` | Whisper-compatible API endpoint |
| `ASR_MODEL` | `medium` | Model name (`medium` / `large-v3` / `whisper-1`) |
| `ASR_API_KEY` | `not-needed` | API key (for cloud ASR) |
| `LLM_BASE_URL` | `http://localhost:18090/v1` | Chat completions API endpoint |
| `LLM_MODEL` | `Qwen3.5-35B-A3B` | Model name |
| `LLM_API_KEY` | `not-needed` | API key (for cloud LLM) |
| `PORT` | `18089` | Service port |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | uni-app (Vue 3) — compiles to both H5 and WeChat Mini Program |
| Backend | FastAPI + SQLite + ChromaDB |
| AI Agent | PydanticAI — tool calling, multi-turn reasoning |
| ASR | Any OpenAI Whisper-compatible API (local or cloud) |
| Speaker | resemblyzer (d-vector) + spectral clustering |
| Vector Search | ChromaDB + bge-base-zh-v1.5 |
| LLM | Any OpenAI Chat-compatible API (local or cloud) |

## License

[Apache-2.0](LICENSE)
