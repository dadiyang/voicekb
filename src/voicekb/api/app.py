"""FastAPI 应用入口。"""

import asyncio
import hashlib
import json as _json
import logging
import uuid as _uuid

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from haloant_kit.log import configure_logging

from voicekb.config import settings
from voicekb.knowledge.agent import create_agent, stream_agent_response
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
_llm = None
_agent = None

# 处理进度追踪: recording_id -> {step, percent}
_progress: dict[str, dict] = {}
# WebSocket 连接: recording_id -> set[WebSocket]
_ws_clients: dict[str, set[WebSocket]] = {}


def _ensure_ready():
    """检查核心服务是否已初始化，未就绪时抛出 503。"""
    if _store is None or _pipeline is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    global _pipeline, _store, _search, _rag, _llm, _agent

    configure_logging(service="voicekb", log_dir=settings.data_dir / "logs")
    settings.ensure_dirs()

    logger.info("VoiceKB 启动中...")

    _pipeline = ProcessingPipeline(settings)
    _store = RecordingStore(settings)
    _search = SearchEngine(settings)

    _llm = create_llm(settings)
    _rag = RAGEngine(_search, _llm)
    _agent = create_agent(settings, search=_search)

    logger.info("VoiceKB 启动完成, 监听 %s:%d", settings.host, settings.port)
    yield

    logger.info("VoiceKB 关闭中...")
    if _store:
        _store.close()
    if _search:
        _search._conn.close()
    if _pipeline and _pipeline.speaker_db:
        _pipeline.speaker_db.close()


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
    deep_think: bool = False

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
    _ensure_ready()

    # 读取文件内容并计算 MD5（用于文件命名，脱敏+去重）
    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    suffix = Path(file.filename or "audio.wav").suffix
    recording_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_hash[:8]}"

    # 保存文件（recording_id 已包含 hash 前缀，不重复附加）
    upload_path = settings.upload_dir / f"{recording_id}{suffix}"
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
    if _pipeline is None or _store is None or _rag is None:
        logger.error("_process_recording 调用时服务未就绪: %s", recording_id)
        return

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
    finally:
        # 处理完成（成功或失败）后延迟清理进度，避免客户端轮询时已无数据
        await asyncio.sleep(30)
        _progress.pop(recording_id, None)


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
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    recordings = _store.list_recordings(limit, offset)
    return [r.model_dump() for r in recordings]


@app.get("/api/recordings/{recording_id}")
async def get_recording(recording_id: str):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
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
    _ensure_ready()

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
    if _store is None or _rag is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")

    rec = _store.get_recording(recording_id)
    if not rec:
        return JSONResponse({"error": "录音不存在"}, status_code=404)
    if not rec.segments:
        return JSONResponse({"error": "该录音没有转写内容"}, status_code=400)

    # 如果标题还是原始文件名，重新生成标题和分类
    if rec.title == rec.filename:
        existing_cats = _store.get_categories()
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
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
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
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    return _store.get_category_presets()

@app.post("/api/categories")
async def add_category(req: CategoryRequest):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.add_category_preset(req.category)
    return {"added": req.category}

@app.post("/api/categories/{preset_id}/delete")
async def delete_category_preset(preset_id: int):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.delete_category_preset(preset_id)
    return {"deleted": True}

@app.post("/api/recordings/{recording_id}/category")
async def update_category(recording_id: str, req: CategoryRequest):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.update_category(recording_id, req.category)
    return {"updated": True}


class RecordingPromptRequest(BaseModel):
    prompt: str

@app.post("/api/recordings/{recording_id}/prompt")
async def set_recording_prompt(recording_id: str, req: RecordingPromptRequest):
    """设置录音级自定义 prompt。"""
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.update_custom_prompt(recording_id, req.prompt)
    return {"updated": True}


class ReassignSegmentRequest(BaseModel):
    start_time: float
    new_speaker_id: str


@app.post("/api/recordings/{recording_id}/reassign-segment")
async def reassign_segment(recording_id: str, req: ReassignSegmentRequest):
    """纠错：将某个时间点的段落改为另一个说话人（只改标签，不改声纹）。"""
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    # 用容差匹配浮点数，避免 IEEE 754 精度问题导致零行更新
    result = _store._conn.execute(
        "UPDATE segments SET speaker_id = ? WHERE recording_id = ? AND ABS(start_time - ?) < 0.05",
        (req.new_speaker_id, recording_id, req.start_time),
    )
    _store._conn.commit()

    # 重新计算并同步该录音的 speakers 列表
    import json as _json_local
    rows = _store._conn.execute(
        "SELECT DISTINCT speaker_id FROM segments WHERE recording_id = ?",
        (recording_id,),
    ).fetchall()
    speakers = [r[0] for r in rows if r[0]]
    _store._conn.execute(
        "UPDATE recordings SET speakers = ? WHERE id = ?",
        (_json_local.dumps(speakers, ensure_ascii=False), recording_id),
    )
    _store._conn.commit()

    return {"updated": result.rowcount, "speakers": speakers}


# ── 摘要 prompt 模板管理 ──────────────────────────────────────────────

class PromptRequest(BaseModel):
    category: str  # "_default" 表示通用模板
    prompt: str

@app.get("/api/summary-prompts")
async def list_summary_prompts():
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    return _store.get_all_summary_prompts()

@app.get("/api/summary-prompts/builtin/{category}")
async def get_builtin_prompt_api(category: str):
    """获取平台内置默认 prompt。"""
    from voicekb.knowledge.rag import get_builtin_prompt
    return {"category": category, "prompt": get_builtin_prompt(category)}

@app.post("/api/summary-prompts")
async def save_summary_prompt(req: PromptRequest):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.save_summary_prompt(req.category, req.prompt)
    return {"saved": True}

@app.post("/api/summary-prompts/{prompt_id}/delete")
async def delete_summary_prompt(prompt_id: int):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.delete_summary_prompt(prompt_id)
    return {"deleted": True}


# ── 术语管理 ──────────────────────────────────────────────────────────

class VocabRequest(BaseModel):
    term: str
    category: str = "person"

@app.get("/api/vocabulary")
async def list_vocabulary():
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    return _store.get_vocabulary()

@app.post("/api/vocabulary")
async def add_vocabulary(req: VocabRequest):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.add_vocabulary(req.term, req.category)
    return {"added": req.term}

@app.post("/api/vocabulary/{term_id}/delete")
async def delete_vocabulary(term_id: int):
    if _store is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    _store.delete_vocabulary(term_id)
    return {"deleted": True}


@app.post("/api/speakers/rename")
async def rename_speaker(req: RenameRequest):
    _ensure_ready()

    # 找到说话人（支持按 id 或 name 匹配）
    speaker_db = _pipeline.speaker_db
    speakers = speaker_db.get_all_speakers()
    old_name = None
    for spk in speakers:
        if spk.name == req.speaker_id or spk.id == req.speaker_id:
            old_name = spk.name
            speaker_db.rename_speaker(spk.id, req.new_name)
            break

    if not old_name:
        return JSONResponse({"error": "说话人不存在"}, status_code=404)

    # 用旧名字更新所有录音中的标注
    count = _store.update_speaker_name(old_name, req.new_name)
    return {"updated_segments": count, "new_name": req.new_name}


@app.post("/api/speakers/{speaker_id}/delete")
async def delete_speaker(speaker_id: str, revert: bool = False):
    """删除说话人。

    - 默认：仅删除声纹档案（以后不再匹配到此人，已有录音标注保留）
    - revert=true：同时把录音中此人的标注恢复为"未知"
    """
    _ensure_ready()

    spk = _pipeline.speaker_db.get_speaker(speaker_id)
    if not spk:
        return JSONResponse({"error": "说话人不存在"}, status_code=404)

    spk_name = spk.name
    _pipeline.speaker_db.delete_speaker(speaker_id)

    if revert:
        _store.revert_speaker_name(spk_name)

    return {"deleted": True, "name": spk_name, "reverted": revert}


@app.get("/api/speakers")
async def list_speakers():
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    speakers = _pipeline.speaker_db.get_all_speakers()
    return [s.model_dump() for s in speakers]


@app.get("/api/search")
async def search(q: str = "", type: str = "hybrid", limit: int = 20):
    if _search is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")

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
    if _rag is None:
        raise HTTPException(status_code=503, detail="服务正在启动，请稍后重试")
    

    conv_id = req.conversation_id or "default"
    db = _ensure_chat_db()

    # 加载历史对话
    rows = db.execute(
        "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall()
    history = [{"role": r[0], "content": r[1]} for r in rows]

    # 调用 RAG（传入历史）
    result = await _rag.answer(req.question, history=history, deep_think=req.deep_think)

    # 保存这轮对话
    db.execute(
        "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, "user", req.question, datetime.now().isoformat()),
    )
    db.execute(
        "INSERT INTO chat_messages (conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?)",
        (conv_id, "assistant", result["answer"],
         _json.dumps(result.get("sources", []), ensure_ascii=False),
         datetime.now().isoformat()),
    )
    db.commit()

    result["conversation_id"] = conv_id
    return result


# ── 流式问答 + 断连恢复 ─────────────────────────────────────────────────

# 已完成的流式结果缓存（request_id → result），最多保留 50 条
_stream_results: dict[str, dict] = {}
_STREAM_CACHE_MAX = 50


@app.post("/api/ask/stream")
async def ask_question_stream(req: AskRequest):
    """SSE 流式问答（PydanticAI Agent）。
    event 类型：request_id / tool_start / tool_end / reasoning / content / done / error
    """
    if _agent is None:
        raise HTTPException(status_code=503, detail="服务正在启动")

    request_id = str(_uuid.uuid4())
    conv_id = req.conversation_id or "default"

    async def event_generator():
        try:
            yield f"event: request_id\ndata: {_json.dumps(request_id)}\n\n"

            full_content = ""
            full_reasoning = ""

            # 加载多轮对话历史
            db = _ensure_chat_db()
            rows = db.execute(
                "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,),
            ).fetchall()
            history = [{"role": r[0], "content": r[1]} for r in rows]

            async for evt in stream_agent_response(
                _agent, req.question, history=history, deep_think=req.deep_think
            ):
                yield f"event: {evt.event}\ndata: {evt.data}\n\n"

                # 累积最终结果
                if evt.event == "content":
                    full_content += _json.loads(evt.data)
                elif evt.event == "reasoning":
                    full_reasoning += _json.loads(evt.data)

            # 保存对话到 chat db（db 已在上面加载历史时获取）
            db.execute(
                "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conv_id, "user", req.question, datetime.now().isoformat()),
            )
            db.execute(
                "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conv_id, "assistant", full_content, datetime.now().isoformat()),
            )
            db.commit()

            # 缓存结果（断连恢复用）
            result = {"answer": full_content}
            if full_reasoning:
                result["reasoning"] = full_reasoning
            _stream_results[request_id] = result
            if len(_stream_results) > _STREAM_CACHE_MAX:
                oldest = next(iter(_stream_results))
                del _stream_results[oldest]

        except Exception:
            logger.error("流式问答失败", exc_info=True)
            yield f"event: error\ndata: {_json.dumps('服务异常，请重试')}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/ask/{request_id}")
async def get_stream_result(request_id: str):
    """断连恢复：根据 request_id 获取已完成的流式结果。"""
    result = _stream_results.get(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在或已过期")
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
