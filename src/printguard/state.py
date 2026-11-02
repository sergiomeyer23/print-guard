from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

OK = "ok"
SENT = "enviado"
FAILED = "falha"
UNKNOWN = "unknown"


@dataclass
class DayState:
    day: str
    status: str
    pdf: str | None = None
    job_id: str | None = None
    attempts: int = 0
    error: str | None = None
    updated: str = ""


class StateStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def path(self, day: str) -> Path:
        return self.directory / f"{day}.json"

    def load(self, day: str) -> DayState | None:
        path = self.path(day)
        if not path.exists():
            return None
        try:
            return DayState(**json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            path.replace(path.with_suffix(".json.corrupt"))
            return None

    def save(self, state: DayState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(state), handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path(state.day))
