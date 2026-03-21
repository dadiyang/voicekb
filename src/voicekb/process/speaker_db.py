"""声纹库 — 持久化的说话人注册和匹配。"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from voicekb.models import Speaker

logger = logging.getLogger(__name__)


class SpeakerDB:
    """SQLite 持久化的声纹库。"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS speakers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                embedding TEXT NOT NULL,
                recording_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def register_speaker(self, name: str, embedding: np.ndarray,
                         recording_id: str = "") -> Speaker:
        """注册新说话人。"""
        speaker_id = f"spk_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        recording_ids = [recording_id] if recording_id else []
        now = datetime.now()

        self._conn.execute(
            "INSERT INTO speakers (id, name, embedding, recording_ids, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (speaker_id, name, json.dumps(embedding.tolist()),
             json.dumps(recording_ids), now.isoformat()),
        )
        self._conn.commit()

        logger.info("注册说话人: %s (%s)", name, speaker_id)
        return Speaker(
            id=speaker_id, name=name,
            embedding=embedding.tolist(),
            recording_ids=recording_ids,
            created_at=now,
        )

    def match_speaker(self, embedding: np.ndarray,
                      threshold: float = 0.85) -> Speaker | None:
        """用余弦相似度匹配已注册的说话人。"""
        speakers = self.get_all_speakers()
        if not speakers:
            return None

        best_match: Speaker | None = None
        best_sim = -1.0

        for spk in speakers:
            spk_embed = np.array(spk.embedding).reshape(1, -1)
            query_embed = embedding.reshape(1, -1)
            sim = float(cosine_similarity(query_embed, spk_embed)[0, 0])
            if sim > best_sim:
                best_sim = sim
                best_match = spk

        if best_match and best_sim >= threshold:
            logger.info("匹配说话人: %s (相似度=%.3f)", best_match.name, best_sim)
            return best_match

        return None

    def rename_speaker(self, speaker_id: str, new_name: str) -> None:
        """重命名说话人。"""
        self._conn.execute(
            "UPDATE speakers SET name = ? WHERE id = ?",
            (new_name, speaker_id),
        )
        self._conn.commit()
        logger.info("重命名说话人 %s -> %s", speaker_id, new_name)

    def add_recording_to_speaker(self, speaker_id: str,
                                 recording_id: str) -> None:
        """将录音关联到说话人。"""
        row = self._conn.execute(
            "SELECT recording_ids FROM speakers WHERE id = ?",
            (speaker_id,),
        ).fetchone()
        if not row:
            return

        ids = json.loads(row["recording_ids"])
        if recording_id not in ids:
            ids.append(recording_id)
            self._conn.execute(
                "UPDATE speakers SET recording_ids = ? WHERE id = ?",
                (json.dumps(ids), speaker_id),
            )
            self._conn.commit()

    def update_embedding(self, speaker_id: str,
                         new_embedding: np.ndarray,
                         momentum: float = 0.3) -> None:
        """用滑动平均更新说话人嵌入。"""
        row = self._conn.execute(
            "SELECT embedding FROM speakers WHERE id = ?",
            (speaker_id,),
        ).fetchone()
        if not row:
            return

        old_embed = np.array(json.loads(row["embedding"]))
        updated = (1 - momentum) * old_embed + momentum * new_embedding
        updated = updated / np.linalg.norm(updated)  # 归一化

        self._conn.execute(
            "UPDATE speakers SET embedding = ? WHERE id = ?",
            (json.dumps(updated.tolist()), speaker_id),
        )
        self._conn.commit()

    def get_all_speakers(self) -> list[Speaker]:
        """获取所有已注册的说话人。"""
        rows = self._conn.execute("SELECT * FROM speakers").fetchall()
        return [
            Speaker(
                id=r["id"],
                name=r["name"],
                embedding=json.loads(r["embedding"]),
                recording_ids=json.loads(r["recording_ids"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def get_speaker(self, speaker_id: str) -> Speaker | None:
        """获取单个说话人。"""
        row = self._conn.execute(
            "SELECT * FROM speakers WHERE id = ?", (speaker_id,),
        ).fetchone()
        if not row:
            return None
        return Speaker(
            id=row["id"],
            name=row["name"],
            embedding=json.loads(row["embedding"]),
            recording_ids=json.loads(row["recording_ids"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        self._conn.close()
