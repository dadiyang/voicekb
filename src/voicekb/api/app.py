"""FastAPI 应用入口。"""

import asyncio
import logging
import shutil
import uuid
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


app = FastAPI(title="VoiceKB", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 静态文件（H5 前端）
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


# ── 请求/响应模型 ────────────────────────────────────────────────────────

class RenameRequest(BaseModel):
    speaker_id: str
    new_name: str

class AskRequest(BaseModel):
    question: str


# ── API 路由 ──────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    """返回 H5 首页。"""
    html_path = web_dir / "index.html"
    if html_path.exists():
        from fastapi.responses import HTMLResponse
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

    recording_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 保存文件
    upload_path = settings.upload_dir / f"{recording_id}_{file.filename}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 创建 pending 记录
    from voicekb.models import Recording
    rec = Recording(
        id=recording_id,
        filename=file.filename or "unknown.wav",
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

        # 生成摘要
        _progress[recording_id] = {"step": "生成摘要", "percent": 92}
        summary = await _rag.summarize_recording(recording)
        recording.summary = summary

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


@app.post("/api/ask")
async def ask_question(req: AskRequest):
    assert _rag is not None
    result = await _rag.answer(req.question)
    return result


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
