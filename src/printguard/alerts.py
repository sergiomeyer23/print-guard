from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


class Alerter:
    def __init__(self, directory: Path, event_log: bool = False):
        self.directory = directory
        self.event_log = event_log

    def path(self, day: str) -> Path:
        return self.directory / f"ALERTA_{day}.txt"

    def raise_alert(self, day: str, message: str, now: datetime) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(day)
        if self._last_message(path) == message:
            return path
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now:%Y-%m-%d %H:%M:%S}] {message}\n")
        if self.event_log:
            write_event_log(message)
        return path

    @staticmethod
    def _last_message(path: Path) -> str | None:
        if not path.exists():
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        return lines[-1].split("] ", 1)[-1] if lines else None


def write_event_log(message: str) -> bool:
    if sys.platform != "win32":
        return False
    result = subprocess.run(
        [
            "eventcreate",
            "/L",
            "APPLICATION",
            "/T",
            "ERROR",
            "/ID",
            "100",
            "/SO",
            "printguard",
            "/D",
            message[:2000],
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
