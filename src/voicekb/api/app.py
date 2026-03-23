"""FastAPI 应用入口。"""

import asyncio
import logging
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from haloant_kit.log import configure_logging

from voicekb.config import settings
from voicekb.knowledge.llm import create_llm
from voicekb.knowledge.rag import RAGEngine
from voicekb.knowledge.search import SearchEngine
from voicekb.knowledge.store import RecordingStore
from voicekb.process.pipeline import ProcessingPipeline

logger = logging.getLogger(__name__)

# ── 全局状态 ──────────────────────────────────────────────────────────────
_pipeline: ProcessingPipeline | None = None
_store: RecordingStore | None = None
_search: SearchEngine | None = None
_rag: RAGEngine | None = None

# 处理进度追踪: recording_id -> {step, percent}
_progress: dict[str, dict] = {}
# WebSocket 连接: recording_id -> set[WebSocket]
_ws_clients: dict[str, set[WebSocket]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    global _pipeline, _store, _search, _rag

    configure_logging(service="voicekb", log_dir=settings.data_dir / "logs")
    settings.ensure_dirs()

    logger.info("VoiceKB 启动中...")

    _pipeline = ProcessingPipeline(settings)
    _store = RecordingStore(settings)
    _search = SearchEngine(settings)

    llm = create_llm(settings)
    _rag = RAGEngine(_search, llm)

    logger.info("VoiceKB 启动完成, 监听 %s:%d", settings.host, settings.port)
    yield

    logger.info("VoiceKB 关闭中...")


app = FastAPI(
    title="VoiceKB",
    description="Personal voice recording knowledge base with ASR, speaker diarization, and RAG-based Q&A",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 静态文件 — uni-app H5 构建产物（优先）或 fallback 到旧版
h5_dir = Path(__file__).parent.parent.parent.parent / "client" / "dist" / "build" / "h5"
web_dir = Path(__file__).parent.parent / "web"
_frontend_dir = h5_dir if h5_dir.exists() else web_dir

# 挂载 assets/ 目录（uni-app 构建的 JS/CSS）
_assets_dir = _frontend_dir / "assets" if _frontend_dir.exists() else None
if _assets_dir and _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

# 挂载 static/ 目录
_static_sub = _frontend_dir / "static" if _frontend_dir.exists() else None
if _static_sub and _static_sub.exists():
    app.mount("/static", StaticFiles(directory=str(_static_sub)), name="static")



# ── 请求/响应模型 ────────────────────────────────────────────────────────

class RenameRequest(BaseModel):
    speaker_id: str
    new_name: str

class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None

class CategoryRequest(BaseModel):
    category: str


# ── API 路由 ──────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    """返回 H5 首页。"""
    from fastapi.responses import HTMLResponse
    html_path = _frontend_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return {"message": "VoiceKB API"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/recordings/{recording_id}/audio")
async def get_audio(recording_id: str):
    """返回录音的音频文件用于播放。"""
    from fastapi.responses import FileResponse

    # 在 uploads 目录中查找匹配的文件
    mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
                ".flac": "audio/flac", ".ogg": "audio/ogg", ".aac": "audio/aac"}
    for f in settings.upload_dir.iterdir():
        if f.name.startswith(recording_id):
            mime = mime_map.get(f.suffix.lower(), "audio/mpeg")
            return FileResponse(f, media_type=mime)
    return JSONResponse({"error": "音频文件不存在"}, status_code=404)


@app.post("/api/upload")
async def upload_audio(file: UploadFile = File(...)):
    """上传音频文件并启动后台处理。"""
    assert _store is not None
    assert _pipeline is not None

    # 读取文件内容并计算 MD5（用于文件命名，脱敏+去重）
    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    suffix = Path(file.filename or "audio.wav").suffix
    recording_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_hash[:8]}"

    # 保存文件（recording_id + hash，不含原始文件名）
    upload_path = settings.upload_dir / f"{recording_id}_{file_hash[:8]}{suffix}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    with open(upload_path, "wb") as f:
        f.write(content)

    # 创建 pending 记录
    from voicekb.models import Recording
    rec = Recording(
        id=recording_id,
        filename=file.filename or "recording.wav",  # 原始文件名（展示用，标题生成前的 fallback）
        source="upload",
        status="processing",
        created_at=datetime.now(),
    )
    _store.save_recording(rec)
    _progress[recording_id] = {"step": "排队中", "percent": 0}

    # 启动后台处理
    asyncio.create_task(_process_recording(recording_id, upload_path))

    return {"recording_id": recording_id, "status": "processing"}


async def _process_recording(recording_id: str, audio_path: Path) -> None:
    """后台处理录音。"""
    assert _pipeline is not None
    assert _store is not None
    assert _rag is not None

    loop = asyncio.get_event_loop()

    def progress_cb(step: str, pct: int) -> None:
        _progress[recording_id] = {"step": step, "percent": pct}
        # 跨线程安全地调度 WebSocket 广播
        try:
            loop.call_soon_threadsafe(
                asyncio.ensure_future,
                _broadcast_progress(recording_id, step, pct),
            )
        except RuntimeError:
            pass  # loop closed

    try:
        _store.update_recording_status(recording_id, "processing")

        # 在线程池中运行 CPU/GPU 密集型处理
        recording = await loop.run_in_executor(
            None, _pipeline.process, audio_path, recording_id, progress_cb,
        )

        # LLM 第 1 步：标题 + 分类
        _progress[recording_id] = {"step": "正在分析内容...", "percent": 70}
        presets = _store.get_category_presets()
        existing_cats = [p["name"] for p in presets]
        title, category = await _rag.classify_and_title(recording, existing_cats)
        recording.title = title
        recording.category = category

        # LLM 第 2+3 步：总结和润色并行执行（互不依赖）
        _progress[recording_id] = {"step": "正在生成摘要和润色文本...", "percent": 75}
        existing_rec = _store.get_recording(recording_id)
        rec_prompt = existing_rec.custom_prompt if existing_rec else ""
        custom_prompt = rec_prompt or _store.get_summary_prompt(category)

        async def _do_summary():
            return await _rag.summarize_recording(recording, custom_prompt=custom_prompt)

        async def _do_polish():
            try:
                return await _rag.polish_segments(recording.segments)
            except Exception:
                logger.error("润色转写失败，保留原文", exc_info=True)
                return recording.segments

        summary_result, polished_result = await asyncio.gather(_do_summary(), _do_polish())

        recording.summary = summary_result
        if rec_prompt:
            recording.custom_prompt = rec_prompt
        recording.segments = polished_result
        _progress[recording_id] = {"step": "即将完成...", "percent": 98}

        # 保存结果
        _store.save_recording(recording)
        progress_cb("处理完成", 100)

    except Exception:
        logger.error("处理录音失败: %s", recording_id, exc_info=True)
        _store.update_recording_status(recording_id, "failed", error="处理失败")
        _progress[recording_id] = {"step": "处理失败", "percent": -1}


async def _broadcast_progress(recording_id: str, step: str, pct: int) -> None:
    """向 WebSocket 客户端广播进度。"""
    clients = _ws_clients.get(recording_id, set())
    dead = set()
    for ws in clients:
        try:
            await ws.send_json({"step": step, "percent": pct})
        except Exception:
            dead.add(ws)
    clients -= dead


@app.get("/api/recordings")
async def list_recordings(limit: int = 50, offset: int = 0):
    assert _store is not None
    recordings = _store.list_recordings(limit, offset)
    return [r.model_dump() for r in recordings]


@app.get("/api/recordings/{recording_id}")
async def get_recording(recording_id: str):
    assert _store is not None
    rec = _store.get_recording(recording_id)
    if not rec:
        return JSONResponse({"error": "录音不存在"}, status_code=404)
    return rec.model_dump()


@app.get("/api/recordings/{recording_id}/status")
async def get_recording_status(recording_id: str):
    progress = _progress.get(recording_id, {"step": "未知", "percent": 0})
    return progress


@app.post("/api/recordings/{recording_id}/reprocess")
async def reprocess_recording(recording_id: str):
    """重新处理录音（使用最新术语库）。"""
    assert _store is not None

    # 找到原始音频文件
    audio_path = None
    for f in settings.upload_dir.iterdir():
        if f.name.startswith(recording_id):
            audio_path = f
            break

    if not audio_path:
        return JSONResponse({"error": "原始音频文件不存在"}, status_code=404)

    _store.update_recording_status(recording_id, "processing")
    _progress[recording_id] = {"step": "排队中", "percent": 0}

    asyncio.create_task(_process_recording(recording_id, audio_path))
    return {"recording_id": recording_id, "status": "processing"}


@app.post("/api/recordings/{recording_id}/resummarize")
async def resummarize_recording(recording_id: str):
    """仅重新生成摘要（不重跑 ASR 和声纹，几秒钟完成）。"""
    assert _store is not None
    assert _rag is not None

    rec = _store.get_recording(recording_id)
    if not rec:
        return JSONResponse({"error": "录音不存在"}, status_code=404)
    if not rec.segments:
        return JSONResponse({"error": "该录音没有转写内容"}, status_code=400)

    # 如果标题还是原始文件名，重新生成标题和分类
    if rec.title == rec.filename:
        existing_cats = [c.name if hasattr(c, 'name') else c for c in _store.get_categories()]
        title, category = await _rag.classify_and_title(rec, existing_cats)
        rec.title = title
        if category:
            rec.category = category

    # 三层 prompt 优先级
    custom_prompt = rec.custom_prompt or _store.get_summary_prompt(rec.category)
    summary = await _rag.summarize_recording(rec, custom_prompt=custom_prompt)
    rec.summary = summary
    _store.save_recording(rec)

    return {"recording_id": recording_id, "summary_length": len(summary)}


@app.post("/api/recordings/{recording_id}/delete")
async def delete_recording(recording_id: str):
    """删除录音及其所有数据。"""
    assert _store is not None
    rec = _store.get_recording(recording_id)
    if not rec:
        return JSONResponse({"error": "录音不存在"}, status_code=404)

    # 删除音频文件
    for f in settings.upload_dir.iterdir():
        if f.name.startswith(recording_id):
            f.unlink(missing_ok=True)

    # 删除 Markdown
    md = settings.markdown_dir / f"{recording_id}.md"
    md.unlink(missing_ok=True)

    # 删除数据库记录（CASCADE 会删 segments）
    _store._conn.execute("DELETE FROM segments WHERE recording_id = ?", (recording_id,))
    _store._conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    _store._conn.commit()

    # 删除 ChromaDB 索引
    try:
        col = _store._get_chroma()
        existing = col.get(where={"recording_id": recording_id})
        if existing and existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception:
        logger.warning("清理向量索引失败: %s", recording_id, exc_info=True)

    logger.info("删除录音: %s", recording_id)
    return {"deleted": True}


# ── 分类 ──────────────────────────────────────────────────────────────

@app.get("/api/categories")
async def list_categories():
    """返回所有分类预置。"""
    assert _store is not None
    return _store.get_category_presets()

@app.post("/api/categories")
async def add_category(req: CategoryRequest):
    assert _store is not None
    _store.add_category_preset(req.category)
    return {"added": req.category}

@app.post("/api/categories/{preset_id}/delete")
async def delete_category_preset(preset_id: int):
    assert _store is not None
    _store.delete_category_preset(preset_id)
    return {"deleted": True}

@app.post("/api/recordings/{recording_id}/category")
async def update_category(recording_id: str, req: CategoryRequest):
    assert _store is not None
    _store.update_category(recording_id, req.category)
    return {"updated": True}


class RecordingPromptRequest(BaseModel):
    prompt: str

@app.post("/api/recordings/{recording_id}/prompt")
async def set_recording_prompt(recording_id: str, req: RecordingPromptRequest):
    """设置录音级自定义 prompt。"""
    assert _store is not None
    _store._conn.execute(
        "UPDATE recordings SET custom_prompt = ? WHERE id = ?",
        (req.prompt, recording_id),
    )
    _store._conn.commit()
    return {"updated": True}


# ── 摘要 prompt 模板管理 ──────────────────────────────────────────────

class PromptRequest(BaseModel):
    category: str  # "_default" 表示通用模板
    prompt: str

@app.get("/api/summary-prompts")
async def list_summary_prompts():
    assert _store is not None
    return _store.get_all_summary_prompts()

@app.get("/api/summary-prompts/builtin/{category}")
async def get_builtin_prompt_api(category: str):
    """获取平台内置默认 prompt。"""
    from voicekb.knowledge.rag import get_builtin_prompt
    return {"category": category, "prompt": get_builtin_prompt(category)}

@app.post("/api/summary-prompts")
async def save_summary_prompt(req: PromptRequest):
    assert _store is not None
    _store.save_summary_prompt(req.category, req.prompt)
    return {"saved": True}

@app.post("/api/summary-prompts/{prompt_id}/delete")
async def delete_summary_prompt(prompt_id: int):
    assert _store is not None
    _store.delete_summary_prompt(prompt_id)
    return {"deleted": True}


# ── 术语管理 ──────────────────────────────────────────────────────────

class VocabRequest(BaseModel):
    term: str
    category: str = "general"

@app.get("/api/vocabulary")
async def list_vocabulary():
    assert _store is not None
    return _store.get_vocabulary()

@app.post("/api/vocabulary")
async def add_vocabulary(req: VocabRequest):
    assert _store is not None
    _store.add_vocabulary(req.term, req.category)
    return {"added": req.term}

@app.post("/api/vocabulary/{term_id}/delete")
async def delete_vocabulary(term_id: int):
    assert _store is not None
    _store.delete_vocabulary(term_id)
    return {"deleted": True}


@app.post("/api/speakers/rename")
async def rename_speaker(req: RenameRequest):
    assert _store is not None
    assert _pipeline is not None

    # 更新声纹库
    speaker_db = _pipeline.speaker_db
    speakers = speaker_db.get_all_speakers()
    for spk in speakers:
        if spk.name == req.speaker_id or spk.id == req.speaker_id:
            speaker_db.rename_speaker(spk.id, req.new_name)
            break

    # 更新所有录音中的说话人名称
    count = _store.update_speaker_name(req.speaker_id, req.new_name)
    return {"updated_segments": count, "new_name": req.new_name}


@app.get("/api/speakers")
async def list_speakers():
    assert _pipeline is not None
    speakers = _pipeline.speaker_db.get_all_speakers()
    return [s.model_dump() for s in speakers]


@app.get("/api/search")
async def search(q: str = "", type: str = "hybrid", limit: int = 20):
    assert _search is not None

    if not q:
        return []

    if type == "keyword":
        results = _search.keyword_search(q, limit)
    elif type == "semantic":
        results = _search.semantic_search(q, limit)
    else:
        results = _search.hybrid_search(q, limit)

    return [r.model_dump() for r in results]


# ── 对话历史存储 ──────────────────────────────────────────────────────────
import json as _json
import sqlite3 as _sqlite3

def _get_chat_db():
    db = _sqlite3.connect(str(settings.data_dir / "chat.db"), check_same_thread=False)
    db.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources TEXT DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_conv ON chat_messages(conversation_id)")
    db.commit()
    return db

_chat_db = None

def _ensure_chat_db():
    global _chat_db
    if _chat_db is None:
        _chat_db = _get_chat_db()
    return _chat_db


@app.post("/api/ask")
async def ask_question(req: AskRequest):
    assert _rag is not None
    from datetime import datetime as _dt

    conv_id = req.conversation_id or "default"
    db = _ensure_chat_db()

    # 加载历史对话
    rows = db.execute(
        "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall()
    history = [{"role": r[0], "content": r[1]} for r in rows]

    # 调用 RAG（传入历史）
    result = await _rag.answer(req.question, history=history)

    # 保存这轮对话
    db.execute(
        "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, "user", req.question, _dt.now().isoformat()),
    )
    db.execute(
        "INSERT INTO chat_messages (conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?)",
        (conv_id, "assistant", result["answer"],
         _json.dumps(result.get("sources", []), ensure_ascii=False),
         _dt.now().isoformat()),
    )
    db.commit()

    result["conversation_id"] = conv_id
    return result


@app.get("/api/chat/history")
async def get_chat_history(conversation_id: str = "default", limit: int = 50):
    """获取对话历史。"""
    db = _ensure_chat_db()
    rows = db.execute(
        "SELECT role, content, sources, created_at FROM chat_messages "
        "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    rows.reverse()
    return [
        {"role": r[0], "content": r[1],
         "sources": _json.loads(r[2]) if r[2] else [],
         "created_at": r[3]}
        for r in rows
    ]


@app.post("/api/chat/clear")
async def clear_chat(conversation_id: str = "default"):
    """清空对话历史。"""
    db = _ensure_chat_db()
    db.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conversation_id,))
    db.commit()
    return {"cleared": True}


# ── WebSocket 进度推送 ───────────────────────────────────────────────────

@app.websocket("/ws/progress/{recording_id}")
async def ws_progress(websocket: WebSocket, recording_id: str):
    await websocket.accept()

    if recording_id not in _ws_clients:
        _ws_clients[recording_id] = set()
    _ws_clients[recording_id].add(websocket)

    try:
        # 发送当前进度
        progress = _progress.get(recording_id, {"step": "等待中", "percent": 0})
        await websocket.send_json(progress)

        # 保持连接直到关闭
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.get(recording_id, set()).discard(websocket)
