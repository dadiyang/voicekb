"""存储引擎 — SQLite + Markdown + ChromaDB 三写。"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from voicekb.config import Settings
from voicekb.models import Recording, Segment

logger = logging.getLogger(__name__)


class RecordingStore:
    """录音数据的持久化存储。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        settings.ensure_dirs()

        self._db_path = settings.db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

        # ChromaDB 懒加载
        self._chroma_collection = None

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS recordings (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'upload',
                duration REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                summary TEXT DEFAULT '',
                category TEXT DEFAULT '',
                custom_prompt TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                error TEXT,
                speakers TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                text TEXT NOT NULL,
                text_polished TEXT DEFAULT '',
                speaker_id TEXT NOT NULL,
                confidence REAL DEFAULT 1.0
            );

            CREATE INDEX IF NOT EXISTS idx_segments_recording
                ON segments(recording_id);
        """)

        # 自定义术语表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT 'person'
            )
        """)

        # 摘要 prompt 模板表（按分类自定义）
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS summary_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                prompt TEXT NOT NULL
            )
        """)

        # 录音分类预置表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS category_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_builtin INTEGER DEFAULT 0
            )
        """)
        # 预置分类（仅首次）
        builtins = ["工作会议", "项目讨论", "技术评审", "日常聊天", "电话沟通", "培训讲座", "面试", "其他"]
        for cat in builtins:
            try:
                self._conn.execute(
                    "INSERT INTO category_presets (name, is_builtin) VALUES (?, 1)", (cat,))
            except sqlite3.IntegrityError:
                pass
        self._conn.commit()

        # FTS5 — 需要单独处理（不能在 executescript 中和其他语句混合）
        try:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts
                USING fts5(text, content=segments, content_rowid=id)
            """)
        except sqlite3.OperationalError:
            pass  # 已存在

        # FTS 同步触发器
        for trigger_sql in [
            """CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
                INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
            END""",
            """CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
                INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
            END""",
            """CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
                INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
                INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
            END""",
        ]:
            try:
                self._conn.execute(trigger_sql)
            except sqlite3.OperationalError:
                pass

        self._conn.commit()

    def _get_chroma(self):
        """懒加载 ChromaDB。"""
        if self._chroma_collection is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.PersistentClient(
                path=str(self._settings.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._chroma_collection = client.get_or_create_collection(
                name="segments",
                metadata={"hnsw:space": "cosine"},
            )
        return self._chroma_collection

    def save_recording(self, recording: Recording) -> None:
        """保存录音到 SQLite + Markdown + ChromaDB。"""
        # SQLite
        self._conn.execute(
            "INSERT OR REPLACE INTO recordings "
            "(id, filename, title, source, duration, created_at, status, summary, category, custom_prompt, tags, error, speakers) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (recording.id, recording.filename, recording.title,
             recording.source, recording.duration,
             recording.created_at.isoformat(),
             recording.status, recording.summary, recording.category,
             recording.custom_prompt,
             json.dumps(recording.tags), recording.error,
             json.dumps(recording.speakers)),
        )

        # 删除旧 segments（覆盖更新）
        self._conn.execute(
            "DELETE FROM segments WHERE recording_id = ?", (recording.id,),
        )

        for seg in recording.segments:
            self._conn.execute(
                "INSERT INTO segments (recording_id, start_time, end_time, text, text_polished, speaker_id, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (recording.id, seg.start, seg.end, seg.text,
                 seg.text_polished, seg.speaker_id, seg.confidence),
            )

        self._conn.commit()

        # Markdown
        self._write_markdown(recording)

        # ChromaDB
        self._index_to_chroma(recording)

        logger.info("保存录音: %s (%d 个片段)", recording.id, len(recording.segments))

    def update_recording_status(self, recording_id: str, status: str,
                                error: str | None = None) -> None:
        """更新录音处理状态。"""
        self._conn.execute(
            "UPDATE recordings SET status = ?, error = ? WHERE id = ?",
            (status, error, recording_id),
        )
        self._conn.commit()

    def get_recording(self, recording_id: str) -> Recording | None:
        """获取单条录音。"""
        row = self._conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_recording(row)

    def list_recordings(self, limit: int = 50, offset: int = 0) -> list[Recording]:
        """列出所有录音。"""
        rows = self._conn.execute(
            "SELECT * FROM recordings ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_recording(r) for r in rows]

    def update_speaker_name(self, old_name: str, new_name: str) -> int:
        """全局替换说话人名称，返回更新的片段数。"""
        cursor = self._conn.execute(
            "UPDATE segments SET speaker_id = ? WHERE speaker_id = ?",
            (new_name, old_name),
        )
        count = cursor.rowcount

        # 更新 recordings 表的 speakers 字段
        rows = self._conn.execute("SELECT id, speakers FROM recordings").fetchall()
        for r in rows:
            speakers = json.loads(r["speakers"])
            if old_name in speakers:
                speakers = [new_name if s == old_name else s for s in speakers]
                self._conn.execute(
                    "UPDATE recordings SET speakers = ? WHERE id = ?",
                    (json.dumps(speakers), r["id"]),
                )

        self._conn.commit()

        # 重新生成受影响的 Markdown
        affected_ids = self._conn.execute(
            "SELECT DISTINCT recording_id FROM segments WHERE speaker_id = ?",
            (new_name,),
        ).fetchall()
        for row in affected_ids:
            rec = self.get_recording(row["recording_id"])
            if rec:
                self._write_markdown(rec)

        logger.info("全局替换说话人: %s -> %s (%d 条片段)", old_name, new_name, count)
        return count

    def _row_to_recording(self, row: sqlite3.Row) -> Recording:
        segments = self._conn.execute(
            "SELECT * FROM segments WHERE recording_id = ? ORDER BY start_time",
            (row["id"],),
        ).fetchall()

        return Recording(
            id=row["id"],
            filename=row["filename"],
            title=row["title"] if "title" in row.keys() else "",
            category=row["category"] if "category" in row.keys() else "",
            custom_prompt=row["custom_prompt"] if "custom_prompt" in row.keys() else "",
            source=row["source"],
            duration=row["duration"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
            summary=row["summary"] or "",
            tags=json.loads(row["tags"] or "[]"),
            error=row["error"],
            speakers=json.loads(row["speakers"] or "[]"),
            segments=[
                Segment(
                    start=s["start_time"], end=s["end_time"],
                    text=s["text"],
                    text_polished=s["text_polished"] if "text_polished" in s.keys() else "",
                    speaker_id=s["speaker_id"],
                    confidence=s["confidence"],
                )
                for s in segments
            ],
        )

    def _write_markdown(self, recording: Recording) -> None:
        """生成 Markdown 文件。"""
        md_path = self._settings.markdown_dir / f"{recording.id}.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {recording.filename}",
            f"",
            f"- ID: {recording.id}",
            f"- 来源: {recording.source}",
            f"- 时长: {recording.duration / 60:.1f} 分钟",
            f"- 参与者: {', '.join(recording.speakers)}",
            f"- 创建时间: {recording.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"",
        ]

        if recording.summary:
            lines.extend([f"## 摘要", f"", recording.summary, f""])

        lines.extend([f"## 对话记录", f""])

        for seg in recording.segments:
            ts = f"{int(seg.start // 60):02d}:{int(seg.start % 60):02d}"
            lines.append(f"**{seg.speaker_id}** ({ts}): {seg.text}")
            lines.append("")

        md_path.write_text("\n".join(lines), encoding="utf-8")

    def _index_to_chroma(self, recording: Recording) -> None:
        """索引到 ChromaDB 用于语义搜索。"""
        try:
            collection = self._get_chroma()

            # 删除旧索引
            try:
                existing = collection.get(where={"recording_id": recording.id})
                if existing and existing["ids"]:
                    collection.delete(ids=existing["ids"])
            except Exception:
                logger.warning("清理 ChromaDB 旧数据失败", exc_info=True)

            if not recording.segments:
                return

            # 按说话人连续发言合并为 chunk
            chunks = self._merge_segments_to_chunks(recording)

            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                doc_id = f"{recording.id}_chunk_{i}"
                ids.append(doc_id)
                documents.append(chunk["text"])
                metadatas.append({
                    "recording_id": recording.id,
                    "recording_filename": recording.filename,
                    "speaker_id": chunk["speaker_id"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                })

            if ids:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)

        except Exception:
            logger.error("ChromaDB 索引失败", exc_info=True)

    @staticmethod
    def _merge_segments_to_chunks(recording: Recording) -> list[dict]:
        """将同一说话人的连续片段合并为 chunk。"""
        if not recording.segments:
            return []

        chunks: list[dict] = []
        current = {
            "speaker_id": recording.segments[0].speaker_id,
            "start": recording.segments[0].start,
            "end": recording.segments[0].end,
            "text": recording.segments[0].text,
        }

        for seg in recording.segments[1:]:
            if seg.speaker_id == current["speaker_id"]:
                current["end"] = seg.end
                current["text"] += " " + seg.text
            else:
                chunks.append(current)
                current = {
                    "speaker_id": seg.speaker_id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }

        chunks.append(current)
        return chunks

    # ── 分类管理 ──────────────────────────────────────────────────────

    def get_categories(self) -> list[str]:
        """获取所有已有的分类（去重）。"""
        rows = self._conn.execute(
            "SELECT DISTINCT category FROM recordings WHERE category != '' ORDER BY category"
        ).fetchall()
        return [r[0] for r in rows]

    def get_category_presets(self) -> list[dict]:
        """获取所有分类预置（内置+自定义）。"""
        rows = self._conn.execute(
            "SELECT id, name, is_builtin FROM category_presets ORDER BY is_builtin DESC, id"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "is_builtin": bool(r[2])} for r in rows]

    def add_category_preset(self, name: str) -> None:
        """添加自定义分类。"""
        try:
            self._conn.execute(
                "INSERT INTO category_presets (name, is_builtin) VALUES (?, 0)", (name.strip(),))
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass

    def delete_category_preset(self, preset_id: int) -> None:
        """删除自定义分类（内置的不允许删）。"""
        self._conn.execute(
            "DELETE FROM category_presets WHERE id = ? AND is_builtin = 0", (preset_id,))
        self._conn.commit()

    def update_category(self, recording_id: str, category: str) -> None:
        """修改录音分类。"""
        self._conn.execute(
            "UPDATE recordings SET category = ? WHERE id = ?",
            (category, recording_id),
        )
        self._conn.commit()

    # ── 术语管理 ──────────────────────────────────────────────────────

    def get_vocabulary(self) -> list[dict]:
        """获取所有自定义术语。"""
        rows = self._conn.execute(
            "SELECT id, term, category FROM vocabulary ORDER BY category, term"
        ).fetchall()
        return [{"id": r[0], "term": r[1], "category": r[2]} for r in rows]

    def get_hotwords(self) -> list[str]:
        """获取所有术语文本（供 ASR 使用）。"""
        rows = self._conn.execute("SELECT term FROM vocabulary").fetchall()
        return [r[0] for r in rows]

    def add_vocabulary(self, term: str, category: str = "general") -> None:
        """添加术语。"""
        try:
            self._conn.execute(
                "INSERT INTO vocabulary (term, category) VALUES (?, ?)",
                (term.strip(), category),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # 已存在

    def delete_vocabulary(self, term_id: int) -> None:
        """删除术语。"""
        self._conn.execute("DELETE FROM vocabulary WHERE id = ?", (term_id,))
        self._conn.commit()

    # ── 摘要 prompt 模板管理 ────────────────────────────────────────────

    def get_summary_prompt(self, category: str) -> str | None:
        """获取指定分类的自定义摘要 prompt。None 表示使用默认。"""
        row = self._conn.execute(
            "SELECT prompt FROM summary_prompts WHERE category = ?", (category,)
        ).fetchone()
        if row:
            return row[0]
        # 尝试通用 prompt（category="_default"）
        row = self._conn.execute(
            "SELECT prompt FROM summary_prompts WHERE category = '_default'"
        ).fetchone()
        return row[0] if row else None

    def get_all_summary_prompts(self) -> list[dict]:
        """获取所有自定义摘要 prompt。"""
        rows = self._conn.execute(
            "SELECT id, category, prompt FROM summary_prompts ORDER BY category"
        ).fetchall()
        return [{"id": r[0], "category": r[1], "prompt": r[2]} for r in rows]

    def save_summary_prompt(self, category: str, prompt: str) -> None:
        """保存（upsert）摘要 prompt。category="_default" 表示通用模板。"""
        self._conn.execute(
            "INSERT INTO summary_prompts (category, prompt) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET prompt = ?",
            (category, prompt, prompt),
        )
        self._conn.commit()

    def delete_summary_prompt(self, prompt_id: int) -> None:
        self._conn.execute("DELETE FROM summary_prompts WHERE id = ?", (prompt_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
