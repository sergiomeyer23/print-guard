from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol


class JobStatus(Enum):
    QUEUED = "queued"
    PRINTING = "printing"
    DONE = "done"
    ERROR = "error"


class PrinterError(Exception):
    pass


class QueueUnreadable(PrinterError):
    pass


class Printer(Protocol):
    def submit(self, pdf: Path) -> str: ...

    def status(self, job_id: str) -> JobStatus: ...

    def cancel(self, job_id: str) -> None: ...
