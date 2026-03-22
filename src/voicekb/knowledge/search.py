"""搜索引擎 — FTS5 关键词搜索 + ChromaDB 语义搜索。"""

import logging
import sqlite3

from voicekb.config import Settings
from voicekb.models import SearchResult, Segment

logger = logging.getLogger(__name__)


class SearchEngine:
    """混合搜索引擎。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._chroma_collection = None

    def _get_chroma(self):
        if self._chroma_collection is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            client = chromadb.PersistentClient(
                path=str(self._settings.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self._settings.embedding_model,
            )
            self._chroma_collection = client.get_or_create_collection(
                name="segments_v2",
                metadata={"hnsw:space": "cosine"},
                embedding_function=embedding_fn,
            )
        return self._chroma_collection

    def keyword_search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """FTS5 全文搜索。"""
        try:
            # 中文关键词搜索使用 LIKE（FTS5 默认分词器不支持中文）
            rows = self._conn.execute("""
                SELECT s.*, r.filename as recording_filename
                FROM segments s
                JOIN recordings r ON r.id = s.recording_id
                WHERE s.text LIKE ?
                ORDER BY s.start_time
                LIMIT ?
            """, (f"%{query}%", limit)).fetchall()

            return [
                SearchResult(
                    recording_id=r["recording_id"],
                    recording_filename=r["recording_filename"],
                    segment=Segment(
                        start=r["start_time"], end=r["end_time"],
                        text=r["text"], speaker_id=r["speaker_id"],
                        confidence=r["confidence"],
                    ),
                    score=1.0,
                )
                for r in rows
            ]
        except sqlite3.OperationalError:
            logger.error("关键词搜索失败", exc_info=True)
            return []

    def semantic_search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """ChromaDB 向量语义搜索。"""
        try:
            collection = self._get_chroma()
            results = collection.query(
                query_texts=[query],
                n_results=min(limit, collection.count() or 1),
            )

            if not results or not results["ids"] or not results["ids"][0]:
                return []

            search_results: list[SearchResult] = []
            for doc_id, doc, metadata, distance in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                score = 1 - distance  # cosine distance → similarity
                search_results.append(SearchResult(
                    recording_id=metadata["recording_id"],
                    recording_filename=metadata.get("recording_filename", ""),
                    segment=Segment(
                        start=metadata.get("start", 0),
                        end=metadata.get("end", 0),
                        text=doc,
                        speaker_id=metadata.get("speaker_id", ""),
                    ),
                    score=score,
                ))

            return search_results
        except Exception:
            logger.error("语义搜索失败", exc_info=True)
            return []

    def hybrid_search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """语义搜索（bge-base-zh-v1.5 同时覆盖关键词和语义查询）。"""
        results = self.semantic_search(query, limit)
        results = [r for r in results if r.score >= 0.50]
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
