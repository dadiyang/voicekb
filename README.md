# VoiceKB — 个人录音知识库

> 把日常录音变成可搜索、可对话的个人知识库。

VoiceKB 是一个自托管的语音知识管理系统，将录音文件自动处理为带说话人标签的结构化文本，支持关键词搜索、语义搜索和 AI 问答。

## 核心功能

- **语音识别 (ASR)** — 基于 faster-whisper，支持中文，GPU 加速
- **声纹分离** — 自动区分不同说话人，跨录音识别同一人
- **说话人标注** — 给 Speaker_XX 标注真实姓名，全局自动更新
- **知识搜索** — 关键词 + 语义双引擎混合搜索
- **AI 问答** — 基于录音知识库的 RAG 问答（需配置 LLM）
- **H5 移动端** — 手机浏览器即可使用，无需安装 App

## 技术架构

```
消费层: H5 移动端 + REST API
知识层: SQLite FTS + ChromaDB 向量搜索 + LLM RAG
处理层: faster-whisper ASR + resemblyzer 声纹 + 谱聚类
存储层: SQLite + Markdown 双写
```

## 快速开始

```bash
# 1. 创建虚拟环境
python3 -m venv --system-site-packages venv
source venv/bin/activate

# 2. 安装依赖
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  faster-whisper chromadb fastapi uvicorn[standard] \
  python-multipart jinja2 scikit-learn resemblyzer \
  pydantic pydantic-settings aiofiles websockets \
  sentence-transformers

# 3. 启动服务
PYTHONPATH=src python -m uvicorn voicekb.api.app:app \
  --host 0.0.0.0 --port 8080

# 4. 手机浏览器访问 http://<服务器IP>:8080
```

## 配置

通过 `.env` 文件或环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VOICEKB_WHISPER_MODEL` | `small` | Whisper 模型大小 |
| `VOICEKB_WHISPER_DEVICE` | `cuda` | 运行设备 |
| `VOICEKB_LLM_BACKEND` | `none` | LLM 后端 (`openai_compatible` 或 `none`) |
| `VOICEKB_LLM_BASE_URL` | `http://localhost:8000/v1` | LLM API 地址 |
| `VOICEKB_PORT` | `8080` | 服务端口 |

## 系统要求

- Python 3.11+
- NVIDIA GPU (推荐，ASR 和声纹加速)
- 4GB+ VRAM (small 模型) 或 10GB+ (large-v3)
- 8GB+ RAM

## 项目结构

```
src/voicekb/
├── config.py          # 配置管理
├── models.py          # 数据模型
├── process/           # 处理层：ASR + 声纹分离
├── knowledge/         # 知识层：存储 + 搜索 + RAG
├── api/               # API 层：FastAPI
└── web/               # 前端：H5 移动端
```

## 开源协议

MIT
