from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as clock_time
from pathlib import Path

from printguard.alerts import Alerter
from printguard.printers import JobStatus, Printer, PrinterError, QueueUnreadable
from printguard.report import pdf_problem, render_pdf
from printguard.source import fetch_pending
from printguard.state import FAILED, OK, SENT, DayState, StateStore

log = logging.getLogger("printguard")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PENDING = 2


@dataclass
class Config:
    db_path: Path
    state_dir: Path
    out_dir: Path
    alert_dir: Path
    confirm_timeout: float = 120.0
    poll_interval: float = 2.0


class Runner:
    def __init__(
        self,
        config: Config,
        printer: Printer,
        alerter: Alerter,
        now: Callable[[], datetime] = datetime.now,
        sleep: Callable[[float], None] = time.sleep,
        fetch: Callable[[Path, date], list[tuple]] = fetch_pending,
        render: Callable[[list[tuple], Path, datetime], Path] = render_pdf,
    ):
        self.config = config
        self.printer = printer
        self.alerter = alerter
        self.now = now
        self.sleep = sleep
        self.fetch = fetch
        self.render = render
        self.store = StateStore(config.state_dir)

    def run(self) -> int:
        day = self._today()
        state = self.store.load(day)
        if state and state.status == OK:
            log.info("%s already confirmed, nothing to do", day)
            return EXIT_OK
        if state and state.status == SENT:
            return self._confirm(state)
        state = state or DayState(day=day, status=FAILED)
        if not self._release_old_job(state):
            return EXIT_FAILED
        return self._build_and_print(state)

    def print_only(self) -> int:
        day = self._today()
        state = self.store.load(day)
        if state is None or not state.pdf:
            return self._fail(DayState(day=day, status=FAILED), "no report exists for today")
        if not self._release_old_job(state):
            return EXIT_FAILED
        return self._submit(state, Path(state.pdf))

    def check(self, deadline: clock_time | None = None) -> int:
        day = self._today()
        state = self.store.load(day)
        if state and state.status == OK:
            return EXIT_OK
        code = EXIT_FAILED if state and state.status == FAILED else EXIT_PENDING
        if deadline and self.now().time() >= deadline:
            status = state.status if state else "missing"
            self._alert(day, f"no confirmed print by {deadline:%H:%M} (state: {status})")
        return code

    def _build_and_print(self, state: DayState) -> int:
        queried_at = self.now()
        try:
            rows = self.fetch(self.config.db_path, queried_at.date())
            pdf = self.render(rows, self._pdf_path(state.day), queried_at)
        except Exception as exc:
            return self._fail(state, f"could not build report: {exc}")
        return self._submit(state, pdf)

    def _submit(self, state: DayState, pdf: Path) -> int:
        state.pdf = str(pdf)
        state.attempts += 1
        problem = pdf_problem(pdf)
        if problem:
            return self._fail(state, f"refusing to print {pdf.name}: {problem}")
        try:
            state.job_id = self.printer.submit(pdf)
        except PrinterError as exc:
            return self._fail(state, f"submit failed: {exc}")
        state.status, state.error = SENT, None
        self._save(state)
        return self._confirm(state)

    def _confirm(self, state: DayState) -> int:
        try:
            outcome = self._wait_for_job(state.job_id)
        except QueueUnreadable as exc:
            return self._keep_pending(
                state, f"queue unreadable, job {state.job_id} unverified: {exc}"
            )
        if outcome is JobStatus.DONE:
            state.status, state.error = OK, None
            self._save(state)
            log.info("job %s confirmed, state ok", state.job_id)
            return EXIT_OK
        reason = f"job {state.job_id} not confirmed (last status: {outcome.value})"
        self._cancel(state)
        return self._fail(state, reason)

    def _wait_for_job(self, job_id: str) -> JobStatus:
        polls = max(1, math.ceil(self.config.confirm_timeout / self.config.poll_interval))
        status = self.printer.status(job_id)
        for _ in range(polls - 1):
            if status in (JobStatus.DONE, JobStatus.ERROR):
                break
            self.sleep(self.config.poll_interval)
            status = self.printer.status(job_id)
        return status

    def _cancel(self, state: DayState) -> None:
        try:
            self.printer.cancel(state.job_id)
            state.job_id = None
        except PrinterError as exc:
            log.warning("could not cancel job %s: %s", state.job_id, exc)

    def _release_old_job(self, state: DayState) -> bool:
        if not state.job_id:
            return True
        try:
            self.printer.cancel(state.job_id)
        except PrinterError as exc:
            self._fail(state, f"old job {state.job_id} could not be cancelled: {exc}")
            return False
        state.job_id = None
        return True

    def _keep_pending(self, state: DayState, message: str) -> int:
        state.status, state.error = SENT, message
        self._save(state)
        self._alert(state.day, message)
        return EXIT_FAILED

    def _fail(self, state: DayState, message: str) -> int:
        state.status, state.error = FAILED, message
        self._save(state)
        self._alert(state.day, message)
        return EXIT_FAILED

    def _alert(self, day: str, message: str) -> None:
        log.error(message)
        self.alerter.raise_alert(day, message, self.now())

    def _save(self, state: DayState) -> None:
        state.updated = self.now().isoformat(timespec="seconds")
        self.store.save(state)

    def _today(self) -> str:
        return self.now().date().isoformat()

    def _pdf_path(self, day: str) -> Path:
        return self.config.out_dir / f"report_{day}.pdf"
