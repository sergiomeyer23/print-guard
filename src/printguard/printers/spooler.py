from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from printguard.printers.base import JobStatus, PrinterError, QueueUnreadable

PowerShell = Callable[[str], str]

ERROR_FLAGS = ("error", "offline", "paperout", "paperjam", "userintervention", "blocked")
DONE_FLAGS = ("printed", "completed")
ACTIVE_FLAGS = ("printing", "retained")


def run_powershell(script: str) -> str:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PrinterError(f"powershell unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise PrinterError(proc.stderr.strip() or f"powershell exited {proc.returncode}")
    return proc.stdout


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def classify(flags: str) -> JobStatus:
    text = flags.lower()
    if any(flag in text for flag in ERROR_FLAGS):
        return JobStatus.ERROR
    if any(flag in text for flag in DONE_FLAGS):
        return JobStatus.DONE
    if any(flag in text for flag in ACTIVE_FLAGS):
        return JobStatus.PRINTING
    return JobStatus.QUEUED


class WindowsSpoolerPrinter:
    """Sends a PDF through the shell PrintTo verb and watches the Windows print queue."""

    def __init__(
        self,
        printer_name: str,
        powershell: PowerShell = run_powershell,
        sleep: Callable[[float], None] = time.sleep,
        appear_attempts: int = 20,
        appear_interval: float = 0.5,
    ):
        self.printer_name = printer_name
        self.powershell = powershell
        self.sleep = sleep
        self.appear_attempts = appear_attempts
        self.appear_interval = appear_interval

    def submit(self, pdf: Path) -> str:
        before = set(self._jobs())
        self.powershell(
            f"Start-Process -FilePath {quote(str(pdf))} -Verb PrintTo "
            f"-ArgumentList {quote(chr(34) + self.printer_name + chr(34))} -WindowStyle Hidden"
        )
        return self._wait_for_new_job(before)

    def status(self, job_id: str) -> JobStatus:
        jobs = self._jobs()
        if job_id not in jobs:
            return JobStatus.DONE
        return classify(jobs[job_id])

    def cancel(self, job_id: str) -> None:
        self.powershell(
            f"Remove-PrintJob -PrinterName {quote(self.printer_name)} -ID {int(job_id)}"
        )

    def _wait_for_new_job(self, before: set[str]) -> str:
        for _ in range(self.appear_attempts):
            new = sorted(set(self._jobs()) - before, key=int)
            if new:
                return new[-1]
            self.sleep(self.appear_interval)
        raise PrinterError("no new job appeared in the print queue")

    def _jobs(self) -> dict[str, str]:
        script = (
            f"Get-PrintJob -PrinterName {quote(self.printer_name)} | "
            "ForEach-Object { [pscustomobject]@{ID=$_.ID; Status=\"$($_.JobStatus)\"} } | "
            "ConvertTo-Json -Compress"
        )
        try:
            raw = self.powershell(script).strip()
        except PrinterError as exc:
            raise QueueUnreadable(str(exc)) from exc
        return parse_jobs(raw)


def parse_jobs(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise QueueUnreadable(f"unparseable queue output: {raw[:80]!r}") from exc
    if isinstance(data, dict):
        data = [data]
    try:
        return {str(item["ID"]): str(item["Status"]) for item in data}
    except (KeyError, TypeError) as exc:
        raise QueueUnreadable("unexpected queue output shape") from exc
