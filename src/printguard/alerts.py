from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from printguard.printers import PrinterError
from printguard.printers.spooler import PowerShell, quote, run_powershell


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


EVENT_SOURCE = "printguard"
EVENT_ID = 100


def write_event_log(message: str, powershell: PowerShell | None = None) -> bool:
    if sys.platform != "win32":
        return False
    run = powershell or run_powershell
    script = (
        f"Write-EventLog -LogName Application -Source {EVENT_SOURCE} -EntryType Error "
        f"-EventId {EVENT_ID} -Message {quote(message[:30000])}"
    )
    try:
        run(script)
    except PrinterError:
        return False
    return True
