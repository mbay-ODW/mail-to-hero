"""SQLite store for processed-message bookkeeping (idempotency)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    folder TEXT NOT NULL,
    uid INTEGER NOT NULL,
    message_id TEXT,
    contact_id TEXT,
    contact_email TEXT,
    processed_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (folder, uid)
);

CREATE INDEX IF NOT EXISTS processed_message_id ON processed(message_id);
"""


class StateStore:
    """Tracks which (folder, uid) tuples have already been processed."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("StateStore ready at %s", path)

    def is_processed(self, folder: str, uid: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed WHERE folder=? AND uid=?",
            (folder, uid),
        ).fetchone()
        return row is not None

    def mark(
        self,
        folder: str,
        uid: int,
        *,
        message_id: str | None,
        contact_id: str | None,
        contact_email: str | None,
        success: bool,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO processed
                (folder, uid, message_id, contact_id, contact_email,
                 processed_at, success, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder,
                uid,
                message_id,
                contact_id,
                contact_email,
                datetime.utcnow().isoformat(),
                int(success),
                error,
            ),
        )
        self._conn.commit()


__all__ = ["StateStore"]
