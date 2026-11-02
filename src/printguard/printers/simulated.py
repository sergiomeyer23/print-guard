from __future__ import annotations

import json
from pathlib import Path

from printguard.printers.base import JobStatus, PrinterError, QueueUnreadable


class SimulatedPrinter:
    """File-backed fake spooler. Jobs survive process restarts, like a real queue."""

    def __init__(
        self,
        spool_dir: Path,
        ticks: int = 1,
        stuck: bool = False,
        unreadable: bool = False,
    ):
        self.spool_file = spool_dir / "spool.json"
        self.ticks = ticks
        self.stuck = stuck
        self.unreadable = unreadable
        spool_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, pdf: Path) -> str:
        if not pdf.exists():
            raise PrinterError(f"file not found: {pdf}")
        jobs = self._load()
        job_id = f"sim-{len(jobs) + 1}"
        jobs[job_id] = {"pdf": str(pdf), "state": "queued", "polls": 0}
        self._save(jobs)
        return job_id

    def status(self, job_id: str) -> JobStatus:
        jobs = self._load()
        job = jobs.get(job_id)
        if job is None:
            return JobStatus.DONE
        if job["state"] == "cancelled":
            return JobStatus.ERROR
        if job["state"] == "done":
            return JobStatus.DONE
        if self.stuck:
            return JobStatus.QUEUED
        job["polls"] += 1
        if job["polls"] >= self.ticks:
            job["state"] = "done"
            self._save(jobs)
            return JobStatus.DONE
        self._save(jobs)
        return JobStatus.PRINTING

    def cancel(self, job_id: str) -> None:
        jobs = self._load()
        if job_id in jobs:
            jobs[job_id]["state"] = "cancelled"
            self._save(jobs)

    def printed_jobs(self) -> list[str]:
        return [jid for jid, job in self._load().items() if job["state"] == "done"]

    def _load(self) -> dict:
        if self.unreadable:
            raise QueueUnreadable("simulated queue is unreadable")
        if not self.spool_file.exists():
            return {}
        try:
            return json.loads(self.spool_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise QueueUnreadable(f"spool file is corrupt: {exc}") from exc

    def _save(self, jobs: dict) -> None:
        self.spool_file.write_text(json.dumps(jobs), encoding="utf-8")
