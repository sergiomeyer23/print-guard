from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

INTENT = "intent"
SUBMITTED = "submitted"
UNKNOWN = "unknown"
CONFIRMED = "confirmed"
CANCELLED = "cancelled"
REJECTED = "rejected"
ABANDONED = "abandoned"

OPEN_PHASES = (INTENT, SUBMITTED, UNKNOWN)

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    seq INTEGER NOT NULL,
    pdf TEXT NOT NULL,
    baseline TEXT NOT NULL,
    phase TEXT NOT NULL,
    job_id TEXT,
    note TEXT,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    UNIQUE (day, seq)
)
"""

COLUMNS = "id, day, seq, pdf, baseline, phase, job_id, note"


@dataclass(frozen=True)
class Attempt:
    id: int
    day: str
    seq: int
    pdf: str
    baseline: tuple[str, ...]
    phase: str
    job_id: str | None
    note: str | None

    @property
    def is_open(self) -> bool:
        return self.phase in OPEN_PHASES


def _row(row: tuple) -> Attempt:
    return Attempt(
        row[0], row[1], row[2], row[3], tuple(json.loads(row[4])), row[5], row[6], row[7]
    )


class Journal:
    """Write-ahead log of print attempts. Every change is its own committed transaction."""

    def __init__(self, path: Path):
        self.path = path

    def begin(self, day: str, pdf: str, baseline: list[str]) -> Attempt:
        now = _stamp()
        with self._db() as db, db:
            seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM attempts WHERE day = ?", (day,))
            cursor = db.execute(
                "INSERT INTO attempts (day, seq, pdf, baseline, phase, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day, seq.fetchone()[0], pdf, json.dumps(baseline), INTENT, now, now),
            )
            return self._get(db, cursor.lastrowid)

    def set_job(self, attempt_id: int, job_id: str) -> Attempt:
        return self._update(attempt_id, "phase = ?, job_id = ?", (SUBMITTED, job_id))

    def set_phase(self, attempt_id: int, phase: str, note: str | None = None) -> Attempt:
        return self._update(attempt_id, "phase = ?, note = ?", (phase, note))

    def latest(self, day: str) -> Attempt | None:
        with self._db() as db:
            row = db.execute(
                f"SELECT {COLUMNS} FROM attempts WHERE day = ? ORDER BY seq DESC LIMIT 1", (day,)
            ).fetchone()
        return _row(row) if row else None

    def _update(self, attempt_id: int, assignment: str, values: tuple) -> Attempt:
        with self._db() as db, db:
            db.execute(
                f"UPDATE attempts SET {assignment}, updated = ? WHERE id = ?",
                (*values, _stamp(), attempt_id),
            )
            return self._get(db, attempt_id)

    def _get(self, db: sqlite3.Connection, attempt_id: int) -> Attempt:
        row = db.execute(f"SELECT {COLUMNS} FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        return _row(row)

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute(SCHEMA)
        return closing(conn)


def _stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
