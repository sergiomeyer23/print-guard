from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as clock_time
from pathlib import Path

from printguard import journal as j
from printguard.alerts import Alerter
from printguard.journal import Attempt, Journal
from printguard.lock import LockBusy, ProcessLock
from printguard.printers import JobStatus, Printer, PrinterError, QueueUnreadable, SubmitRejected
from printguard.report import pdf_problem, render_pdf
from printguard.source import fetch_pending
from printguard.state import FAILED, OK, SENT, UNKNOWN, DayState, StateStore

log = logging.getLogger("printguard")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PENDING = 2
EXIT_BUSY = 3
EXIT_UNKNOWN = 4

DAY_STATUS = {
    j.INTENT: SENT,
    j.SUBMITTED: SENT,
    j.UNKNOWN: UNKNOWN,
    j.CONFIRMED: OK,
    j.CANCELLED: FAILED,
    j.REJECTED: FAILED,
    j.ABANDONED: FAILED,
}


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
        self.journal = Journal(config.state_dir / "journal.db")
        self.lock = ProcessLock(config.state_dir / "printguard.lock")

    def run(self) -> int:
        return self._locked(self._run)

    def print_only(self) -> int:
        return self._locked(self._print_only)

    def resolve(self, printed: bool) -> int:
        return self._locked(lambda: self._resolve(printed))

    def check(self, deadline: clock_time | None = None) -> int:
        day = self._today()
        state = self._synced_state(day, persist=False)
        if state and state.status == OK:
            return EXIT_OK
        code = {FAILED: EXIT_FAILED, UNKNOWN: EXIT_UNKNOWN}.get(
            state.status if state else "", EXIT_PENDING
        )
        if deadline and self.now().time() >= deadline:
            status = state.status if state else "missing"
            self._alert(day, f"no confirmed print by {deadline:%H:%M} (state: {status})")
        return code

    def _locked(self, action: Callable[[], int]) -> int:
        try:
            self.lock.acquire()
        except LockBusy:
            log.warning("another printguard instance is running, exiting")
            return EXIT_BUSY
        try:
            return action()
        finally:
            self.lock.release()

    def _run(self) -> int:
        day = self._today()
        state = self._synced_state(day)
        if state and state.status == OK:
            log.info("%s already confirmed, nothing to do", day)
            return EXIT_OK
        attempt = self.journal.latest(day)
        if attempt and attempt.is_open:
            return self._recover(state, attempt)
        return self._build_and_print(state or DayState(day=day, status=FAILED))

    def _print_only(self) -> int:
        day = self._today()
        state = self._synced_state(day)
        if state is None or not state.pdf:
            return self._fail(DayState(day=day, status=FAILED), "no report exists for today")
        attempt = self.journal.latest(day)
        if attempt and attempt.is_open:
            log.error(
                "attempt %d is unresolved (%s); recover it before reprinting",
                attempt.seq,
                attempt.phase,
            )
            return EXIT_UNKNOWN if attempt.phase == j.UNKNOWN else EXIT_PENDING
        return self._submit(state, Path(state.pdf))

    def _resolve(self, printed: bool) -> int:
        day = self._today()
        state = self._synced_state(day)
        attempt = self.journal.latest(day)
        if state is None or attempt is None or not attempt.is_open:
            log.error("nothing to resolve for %s", day)
            return EXIT_FAILED
        if printed:
            self.journal.set_phase(attempt.id, j.CONFIRMED, "resolved by operator: printed")
            state.status, state.error = OK, None
        else:
            self._best_effort_cancel(attempt)
            self.journal.set_phase(attempt.id, j.ABANDONED, "resolved by operator: not printed")
            state.status, state.error, state.job_id = (
                FAILED,
                "operator marked the attempt as not printed",
                None,
            )
        self._save(state)
        return EXIT_OK

    def _best_effort_cancel(self, attempt: Attempt) -> None:
        if not attempt.job_id:
            return
        try:
            self.printer.cancel(attempt.job_id)
        except PrinterError as exc:
            log.warning("job %s was not cancelled: %s", attempt.job_id, exc)

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
            baseline = sorted(self.printer.queue())
        except QueueUnreadable as exc:
            return self._fail(state, f"queue unreadable before submit, nothing sent: {exc}")
        attempt = self.journal.begin(state.day, str(pdf), baseline)
        state.status, state.job_id, state.error = SENT, None, None
        self._save(state)
        try:
            job_id = self.printer.submit(pdf)
        except SubmitRejected as exc:
            self.journal.set_phase(attempt.id, j.REJECTED, str(exc))
            return self._fail(state, f"submit failed: {exc}")
        except PrinterError as exc:
            return self._unknown(state, attempt, f"submit outcome unclear: {exc}")
        attempt = self.journal.set_job(attempt.id, job_id)
        state.job_id = job_id
        self._save(state)
        return self._confirm(state, attempt, recovering=False)

    def _recover(self, state: DayState | None, attempt: Attempt) -> int:
        state = state or DayState(day=attempt.day, status=SENT, pdf=attempt.pdf)
        if attempt.job_id is None:
            attempt = self._adopt_job(state, attempt)
            if attempt.job_id is None:
                return EXIT_UNKNOWN
        return self._confirm(state, attempt, recovering=True)

    def _adopt_job(self, state: DayState, attempt: Attempt) -> Attempt:
        try:
            queue = self.printer.queue()
        except QueueUnreadable as exc:
            self._unknown(state, attempt, f"spooler unavailable during recovery: {exc}")
            return attempt
        name = Path(attempt.pdf).name
        fresh = [
            job_id
            for job_id, entry in queue.items()
            if job_id not in attempt.baseline and name in entry.document
        ]
        if len(fresh) == 1:
            state.job_id = fresh[0]
            log.info("recovered job %s for attempt %d from the queue", fresh[0], attempt.seq)
            return self.journal.set_job(attempt.id, fresh[0])
        reason = (
            "several queued jobs match this attempt"
            if fresh
            else "no job for this attempt is in the queue, so a send that never happened "
            "cannot be told apart from one that already printed"
        )
        self._unknown(state, attempt, reason)
        return attempt

    def _confirm(self, state: DayState, attempt: Attempt, recovering: bool) -> int:
        job_id = attempt.job_id
        state.job_id = job_id
        try:
            if recovering and job_id not in self.printer.queue():
                reason = (
                    f"job {job_id} is no longer in the queue; printed and lost cannot be told apart"
                )
                return self._unknown(state, attempt, reason)
            outcome = self._wait_for_job(job_id)
        except QueueUnreadable as exc:
            if recovering:
                return self._unknown(state, attempt, f"spooler unavailable during recovery: {exc}")
            return self._keep_pending(state, f"queue unreadable, job {job_id} unverified: {exc}")
        if outcome is JobStatus.DONE:
            self.journal.set_phase(attempt.id, j.CONFIRMED)
            state.status, state.error = OK, None
            self._save(state)
            log.info("job %s confirmed, state ok", job_id)
            return EXIT_OK
        return self._cancel_unconfirmed(state, attempt, outcome)

    def _cancel_unconfirmed(self, state: DayState, attempt: Attempt, outcome: JobStatus) -> int:
        reason = f"job {attempt.job_id} not confirmed (last status: {outcome.value})"
        try:
            self.printer.cancel(attempt.job_id)
        except PrinterError as exc:
            return self._unknown(
                state, attempt, f"{reason}; cancel failed, it may still print: {exc}"
            )
        self.journal.set_phase(attempt.id, j.CANCELLED, reason)
        state.job_id = None
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

    def _synced_state(self, day: str, persist: bool = True) -> DayState | None:
        state = self.store.load(day)
        attempt = self.journal.latest(day)
        if attempt is None:
            return self._adopt_legacy(state) if persist else state
        derived = DAY_STATUS[attempt.phase]
        if state is None:
            state = DayState(day=day, status=derived, pdf=attempt.pdf, job_id=attempt.job_id)
        if state.status != derived:
            state.status = derived
            if persist:
                self._save(state)
        return state

    def _adopt_legacy(self, state: DayState | None) -> DayState | None:
        if state is None or state.status not in (SENT, UNKNOWN) or not state.pdf:
            return state
        attempt = self.journal.begin(state.day, state.pdf, [])
        if state.job_id:
            self.journal.set_job(attempt.id, state.job_id)
        else:
            self.journal.set_phase(attempt.id, j.UNKNOWN, "imported from an earlier state file")
        return state

    def _keep_pending(self, state: DayState, message: str) -> int:
        state.status, state.error = SENT, message
        self._save(state)
        self._alert(state.day, message)
        return EXIT_FAILED

    def _unknown(self, state: DayState, attempt: Attempt, message: str) -> int:
        self.journal.set_phase(attempt.id, j.UNKNOWN, message)
        state.status, state.error = UNKNOWN, message
        self._save(state)
        self._alert(state.day, f"result unknown, not retrying automatically: {message}")
        return EXIT_UNKNOWN

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
