# VoiceKB Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete, production-ready personal voice knowledge base that processes audio recordings into searchable, AI-queryable knowledge — delivered as an H5 mobile web app.

**Architecture:** Four-layer pipeline (Ingest → Process → Knowledge → Consume) with SQLite + Markdown dual-write storage. Each layer is modular with Protocol-based interfaces. Frontend is a single-page H5 app served by FastAPI.

**Tech Stack:** Python 3.13, FastAPI, faster-whisper (ASR), resemblyzer (speaker embeddings), spectral clustering (diarization), ChromaDB (vector search), SQLite FTS5 (text search), vanilla HTML/CSS/JS (mobile H5 frontend).

**Critical Context:** This is a hackathon competition. Zero human intervention after start. Judges access the running service on mobile browsers. Code quality reviewed by Codex. Must work perfectly end-to-end.

---

## Execution Order and Dependencies

```
Task 1: Config & Models       (foundation — no deps)
Task 2: Process Layer         (depends on 1)
Task 3: Storage Layer         (depends on 1)
Task 4: Knowledge Layer       (depends on 2, 3)
Task 5: API Layer             (depends on 4)
Task 6: H5 Frontend           (depends on 5)
Task 7: Demo Data Seeding     (depends on 2, 3, 4)
Task 8: Startup & Deploy      (depends on all)
Task 9: Playwright E2E Tests  (depends on all — this is the gate)
```

---

### Task 1: Configuration, Models, and Project Skeleton

**Files:**
- Create: `src/voicekb/__init__.py`
- Create: `src/voicekb/config.py`
- Create: `src/voicekb/models.py`
- Create: `pyproject.toml`

**What to build:**

`config.py` — Settings via pydantic-settings, reads `.env`:
```python
class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path("data")
    db_path: Path = Path("data/voicekb.db")
    markdown_dir: Path = Path("data/transcripts")
    upload_dir: Path = Path("data/uploads")
    speaker_db_path: Path = Path("data/speakers.db")

    # ASR
    whisper_model: str = "small"  # or "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"

    # Speaker
    speaker_similarity_threshold: float = 0.85
    max_speakers_per_recording: int = 10

    # LLM
    llm_backend: str = "openai_compatible"  # or "none"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen/Qwen3-8B"
    llm_api_key: str = "not-needed"

    # Search
    chroma_dir: Path = Path("data/chroma")
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = SettingsConfigDict(env_prefix="VOICEKB_", env_file=".env")
```

`models.py` — Pydantic data models used across all layers:
```python
class Segment(BaseModel):
    start: float          # seconds
    end: float
    text: str
    speaker_id: str       # "SPEAKER_00" or registered name
    confidence: float = 1.0

class Recording(BaseModel):
    id: str               # rec_YYYYMMDD_HHMMSS
    filename: str
    source: str           # "upload", "getbiji", etc.
    duration: float       # seconds
    created_at: datetime
    status: str           # "pending", "processing", "completed", "failed"
    segments: list[Segment] = []
    speakers: list[str] = []
    summary: str = ""
    tags: list[str] = []
    error: str | None = None

class Speaker(BaseModel):
    id: str               # spk_xxxxx
    name: str             # "张三" or "Speaker_01"
    embedding: list[float]  # 256-dim d-vector
    recording_ids: list[str] = []
    created_at: datetime

class SearchResult(BaseModel):
    recording_id: str
    recording_filename: str
    segment: Segment
    score: float
    context: list[Segment] = []  # surrounding segments
```

`pyproject.toml` — Standard project metadata with all dependencies listed.

**Test:** `python -c "from voicekb.config import Settings; s = Settings(); print(s.data_dir)"`

**Commit:** `feat: add project skeleton with config and data models`

---

### Task 2: Processing Layer (ASR + Speaker Diarization)

**Files:**
- Create: `src/voicekb/process/__init__.py`
- Create: `src/voicekb/process/asr.py`
- Create: `src/voicekb/process/diarize.py`
- Create: `src/voicekb/process/speaker_db.py`
- Create: `src/voicekb/process/pipeline.py`

**What to build:**

`asr.py` — Wraps faster-whisper:
```python
class ASREngine:
    def __init__(self, model_size: str, device: str, compute_type: str): ...
    def transcribe(self, audio_path: Path, language: str = "zh") -> list[Segment]: ...
```
- Use `vad_filter=True` for built-in VAD
- Return list of `Segment` objects with timestamps

`diarize.py` — Speaker diarization using resemblyzer + spectral clustering:
```python
class Diarizer:
    def __init__(self): ...  # loads VoiceEncoder
    def diarize(self, audio_path: Path, num_speakers: int | None = None) -> list[SpeakerSegment]: ...
    def extract_embedding(self, audio_path: Path, start: float, end: float) -> np.ndarray: ...
```
- Slide 3-second windows with 1.5s overlap over the audio
- Extract d-vector embeddings per window
- Use spectral clustering (auto-detect num_speakers if not provided via eigengap heuristic)
- Return labeled speaker segments

`speaker_db.py` — Persistent speaker registry:
```python
class SpeakerDB:
    def __init__(self, db_path: Path): ...  # SQLite backed
    def register_speaker(self, name: str, embedding: np.ndarray) -> Speaker: ...
    def match_speaker(self, embedding: np.ndarray, threshold: float) -> Speaker | None: ...
    def rename_speaker(self, speaker_id: str, new_name: str) -> None: ...
    def get_all_speakers(self) -> list[Speaker]: ...
    def update_embedding(self, speaker_id: str, new_embedding: np.ndarray) -> None: ...
```
- Cosine similarity matching against registered speakers
- Threshold from config (default 0.85)
- Running average for embedding updates

`pipeline.py` — Orchestrates the full processing:
```python
class ProcessingPipeline:
    def __init__(self, settings: Settings): ...
    async def process(self, audio_path: Path, recording_id: str, progress_callback=None) -> Recording: ...
```
Pipeline steps:
1. ASR transcription (progress: 0-40%)
2. Speaker diarization (progress: 40-70%)
3. Match/register speakers in SpeakerDB (progress: 70-80%)
4. Align ASR segments with speaker labels (progress: 80-90%)
5. Generate summary via LLM if available (progress: 90-100%)

**Key detail:** The `progress_callback` is called with `(step_name, percent)` so the frontend can show progress. Pipeline runs in a background asyncio task.

**Test:** Run pipeline on `data/audio/meeting_product_planning.wav`, verify segments have speaker labels.

**Commit:** `feat: add audio processing pipeline with ASR and speaker diarization`

---

### Task 3: Storage Layer (SQLite + Markdown + ChromaDB)

**Files:**
- Create: `src/voicekb/knowledge/__init__.py`
- Create: `src/voicekb/knowledge/store.py`

**What to build:**

`store.py` — Dual-write storage:
```python
class RecordingStore:
    def __init__(self, settings: Settings): ...
    def init_db(self) -> None: ...  # create tables
    def save_recording(self, recording: Recording) -> None: ...  # SQLite + Markdown + ChromaDB
    def get_recording(self, recording_id: str) -> Recording | None: ...
    def list_recordings(self, limit: int = 50, offset: int = 0) -> list[Recording]: ...
    def update_speaker_name(self, old_name: str, new_name: str) -> int: ...  # returns updated count
    def delete_recording(self, recording_id: str) -> None: ...
```

SQLite schema:
```sql
CREATE TABLE recordings (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'upload',
    duration REAL NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',  -- JSON array
    error TEXT
);

CREATE TABLE segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    speaker_id TEXT NOT NULL,
    confidence REAL DEFAULT 1.0
);

CREATE VIRTUAL TABLE segments_fts USING fts5(text, content=segments, content_rowid=id);

-- Triggers to keep FTS in sync
CREATE TRIGGER segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
```

Markdown output: one `.md` file per recording in `data/transcripts/`.

ChromaDB: index segments with embeddings from `bge-small-zh-v1.5` for semantic search.

**Test:** Save a recording, retrieve it, verify SQLite + Markdown + ChromaDB all have data.

**Commit:** `feat: add recording store with SQLite, Markdown, and ChromaDB`

---

### Task 4: Knowledge Layer (Search + LLM/RAG)

**Files:**
- Create: `src/voicekb/knowledge/search.py`
- Create: `src/voicekb/knowledge/llm.py`
- Create: `src/voicekb/knowledge/rag.py`
- Create: `templates/meeting_summary.j2`
- Create: `templates/daily_summary.j2`
- Create: `templates/rag_answer.j2`

**What to build:**

`search.py` — Hybrid search:
```python
class SearchEngine:
    def __init__(self, settings: Settings): ...
    def keyword_search(self, query: str, limit: int = 20) -> list[SearchResult]: ...  # FTS5
    def semantic_search(self, query: str, limit: int = 20) -> list[SearchResult]: ...  # ChromaDB
    def hybrid_search(self, query: str, limit: int = 20) -> list[SearchResult]: ...   # merge + rerank
```
- Keyword search via FTS5 `MATCH`
- Semantic search via ChromaDB cosine similarity
- Hybrid: union results, rerank by combined score (0.4 * keyword + 0.6 * semantic)

`llm.py` — Pluggable LLM backend:
```python
class LLMBackend(Protocol):
    async def generate(self, prompt: str, max_tokens: int = 2000) -> str: ...

class OpenAICompatibleLLM:
    """Works with vLLM, Ollama, or any OpenAI-compatible API."""
    def __init__(self, base_url: str, model: str, api_key: str): ...
    async def generate(self, prompt: str, max_tokens: int = 2000) -> str: ...

class NoLLM:
    """Fallback when no LLM is configured — returns empty string."""
    async def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        return ""

def create_llm(settings: Settings) -> LLMBackend: ...
```

`rag.py` — RAG question answering:
```python
class RAGEngine:
    def __init__(self, search: SearchEngine, llm: LLMBackend): ...
    async def answer(self, question: str) -> dict: ...  # returns {"answer": str, "sources": list[SearchResult]}
    async def summarize_recording(self, recording: Recording) -> str: ...
```

Templates: Jinja2 templates for summary generation and RAG answers. Include speaker names, timestamps, key decisions, action items.

**IMPORTANT for LLM:** If LLM backend is unavailable, everything else still works. Summary shows "LLM未配置" and RAG returns raw search results without synthesis. Never crash because LLM is down.

**Test:** Run search on seeded data, verify results. Test RAG with and without LLM.

**Commit:** `feat: add search engine and RAG with pluggable LLM`

---

### Task 5: API Layer (FastAPI)

**Files:**
- Create: `src/voicekb/api/__init__.py`
- Create: `src/voicekb/api/app.py`
- Create: `src/voicekb/api/routes.py`

**What to build:**

`app.py` — FastAPI application with lifespan:
```python
app = FastAPI(title="VoiceKB", version="0.1.0")
# Mount static files for H5 frontend
# CORS for mobile access
# Lifespan: init models, DB, speaker_db on startup
```

`routes.py` — All API endpoints (GET and POST only per user preference):

```
POST /api/upload              — Upload audio file, start processing
GET  /api/recordings          — List all recordings
GET  /api/recordings/{id}     — Get recording detail with segments
GET  /api/recordings/{id}/status — Get processing status/progress

POST /api/speakers/rename     — Rename a speaker (body: {speaker_id, new_name})
GET  /api/speakers            — List all registered speakers

GET  /api/search              — Search recordings (query param: q, type=keyword|semantic|hybrid)
POST /api/ask                 — RAG question answering (body: {question})

GET  /api/health              — Health check
```

**Key details:**
- Upload triggers background processing via `asyncio.create_task()`
- Processing status tracked in-memory dict + SQLite
- WebSocket at `/ws/progress/{recording_id}` for real-time progress updates
- All responses are JSON with Chinese-friendly field names in the data

**Test:** `curl` each endpoint, verify responses.

**Commit:** `feat: add FastAPI REST API with all endpoints`

---

### Task 6: H5 Mobile Frontend

**Files:**
- Create: `src/voicekb/web/index.html` — Single HTML file with embedded CSS/JS (simpler to serve, no build step)

**What to build:**

A single-page application (SPA) with these views:
1. **录音列表** (Home) — Cards showing recordings with status, duration, date, speakers
2. **上传** — File picker + upload progress + processing progress
3. **录音详情** — Speaker-labeled transcript timeline + audio player + summary
4. **搜索** — Search input + results list with highlighted matches
5. **AI 问答** — Chat-like interface for RAG queries
6. **说话人管理** — List speakers, rename, see which recordings they appear in

**Design system (from hotel_shop reference):**
- Color: Indigo/blue primary (#4F46E5), slate text (#1D2129), light bg (#F7F8FA)
- Border radius: 12px for cards, 22px for buttons
- Font: system font stack (-apple-system, etc.)
- Mobile-first: 100vw, no horizontal scroll
- Bottom tab navigation (4 tabs: 录音, 搜索, 问答, 我的)
- Cards with subtle shadows
- Loading states with skeleton screens
- Empty states with illustrations (SVG)
- Toast notifications for actions

**Key interactions:**
- Upload: drag-to-upload or tap file picker → progress bar → auto-navigate to detail
- Transcript: scrollable timeline with speaker avatars (colored circles with initials)
- Speaker rename: tap speaker tag → inline edit → save → instant UI update
- Search: debounced input → results with keyword highlighting
- AI chat: message bubbles with typing indicator

**CRITICAL:** This is a SINGLE `index.html` file. No build step, no npm, no framework. Pure HTML + CSS + vanilla JS. FastAPI serves it as a static file. This ensures zero build failures and maximum reliability.

**Test:** Open in mobile viewport, verify all views render correctly.

**Commit:** `feat: add H5 mobile frontend with all views`

---

### Task 7: Demo Data Seeding

**Files:**
- Create: `scripts/seed_demo.py`

**What to build:**

A script that:
1. Stops autoglm-vllm.service (to free GPU memory)
2. Processes `data/audio/meeting_product_planning.wav` through the full pipeline
3. Registers speakers: renames Speaker clusters to 张三, 李四, 王五 based on first-file analysis
4. Processes `data/audio/meeting_tech_review.wav` — verifies 张三 and 王五 are auto-recognized
5. Verifies ChromaDB has indexed segments
6. Verifies FTS5 search works
7. Prints summary of seeded data

This script must be IDEMPOTENT — running it twice doesn't create duplicate data.

**Test:** Run script, verify DB has 2 recordings with correct speaker labels.

**Commit:** `feat: add demo data seeding script`

---

### Task 8: Startup Script and Deployment

**Files:**
- Create: `scripts/start.sh`
- Create: `.env.example`

**What to build:**

`start.sh`:
```bash
#!/bin/bash
# 1. Activate venv
# 2. Stop autoglm-vllm if running
# 3. Start Qwen3-8B via vLLM (optional, controlled by env var)
# 4. Run seed script if DB is empty
# 5. Start FastAPI server with uvicorn
```

Deploy using `~/deploy-tools/bin/deploy voicekb 8080`.

**Test:** Run `start.sh`, verify service is accessible at the deployed URL.

**Commit:** `feat: add startup script and deployment config`

---

### Task 9: Playwright E2E User Journey Tests

**Files:**
- Create: `tests/test_e2e.py`

**What to build:**

Playwright tests implementing the four user journeys from CLAUDE.md:
- Journey A: First use (upload → process → view → rename speaker)
- Journey B: Cross-file recognition (upload second file → verify auto-recognition)
- Journey C: Search (keyword + semantic)
- Journey D: AI Q&A

Each test:
1. Uses iPhone 12 viewport (390x844)
2. Takes screenshots at each step → `tests/screenshots/`
3. Verifies no console errors
4. Verifies no 500 responses

**CRITICAL:** These tests are the FINAL GATE. If any test fails, fix the issue and re-run. Do not declare completion until ALL journeys pass.

**Commit:** `test: add Playwright E2E user journey tests`

---

## Post-Implementation Checklist

After all tasks complete:
1. Run `scripts/seed_demo.py` to verify data pipeline
2. Run `scripts/start.sh` to start the service
3. Run `tests/test_e2e.py` against the running service
4. Fix any failures, re-run tests
5. Deploy to `*.haloant.com`
6. Run E2E tests against deployed URL
7. Create README.md with demo instructions
8. Final git commit and status report
