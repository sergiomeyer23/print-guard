import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

from printguard.cli import main
from printguard.journal import Journal
from printguard.lock import LockBusy, ProcessLock
from printguard.printers import PrinterError, QueueUnreadable, SimulatedPrinter
from printguard.runner import EXIT_BUSY, EXIT_FAILED, EXIT_OK, EXIT_PENDING, EXIT_UNKNOWN
from printguard.state import FAILED, OK, SENT, UNKNOWN, StateStore

DAY = "2026-03-10"
HOLDER = Path(__file__).with_name("lock_holder.py")


class PowerCut(BaseException):
    pass


class DiesBeforeSending(SimulatedPrinter):
    def submit(self, pdf):
        raise PowerCut


class DiesAfterSending(SimulatedPrinter):
    def submit(self, pdf):
        super().submit(pdf)
        raise PowerCut


class AmbiguousSubmit(SimulatedPrinter):
    def submit(self, pdf):
        super().submit(pdf)
        raise PrinterError("powershell timed out")


def spool(config) -> Path:
    return config.out_dir / "spool"


def state(config):
    return StateStore(config.state_dir).load(DAY)


def journal(config):
    return Journal(config.state_dir / "journal.db")


def crash(runner):
    with pytest.raises(PowerCut):
        runner.run()


def mark_job_done(config, job_id="sim-1"):
    path = spool(config) / "spool.json"
    jobs = json.loads(path.read_text())
    jobs[job_id]["state"] = "done"
    path.write_text(json.dumps(jobs))


def test_two_instances_at_once_print_a_single_copy(config, make_runner):
    entered, release = threading.Event(), threading.Event()

    class Gated(SimulatedPrinter):
        def status(self, job_id):
            entered.set()
            assert release.wait(10)
            return super().status(job_id)

    results = {}
    first = threading.Thread(
        target=lambda: results.update(first=make_runner(Gated(spool(config))).run())
    )
    first.start()
    assert entered.wait(10)
    second = make_runner(SimulatedPrinter(spool(config))).run()
    release.set()
    first.join(10)
    assert second == EXIT_BUSY
    assert results["first"] == EXIT_OK
    assert len(SimulatedPrinter(spool(config))._load()) == 1
    assert state(config).status == OK


def test_busy_instance_leaves_no_alert_and_no_state(config, make_runner, alert_file):
    with ProcessLock(config.state_dir / "printguard.lock"):
        assert make_runner().run() == EXIT_BUSY
    assert not alert_file.exists()
    assert state(config) is None


def test_lock_is_exclusive_between_processes_and_recovered_after_kill(tmp_path):
    path = tmp_path / "state" / "printguard.lock"
    holder = subprocess.Popen(
        [sys.executable, str(HOLDER), str(path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(LockBusy):
            ProcessLock(path).acquire()
    finally:
        holder.kill()
        holder.wait(10)
        holder.stdout.close()
    with ProcessLock(path):
        pass


def test_leftover_lock_file_does_not_block(tmp_path):
    path = tmp_path / "printguard.lock"
    path.write_text("pid 99999 from a crashed run")
    with ProcessLock(path):
        pass


def test_intent_is_on_disk_before_the_printer_is_called(config, make_runner):
    seen = {}

    class Inspecting(SimulatedPrinter):
        def submit(self, pdf):
            attempt = journal(config).latest(DAY)
            seen["phase"], seen["state"] = attempt.phase, state(config).status
            return super().submit(pdf)

    make_runner(Inspecting(spool(config))).run()
    assert seen == {"phase": "intent", "state": SENT}


def test_crash_before_sending_becomes_unknown_and_is_not_resent(config, make_runner, alert_file):
    crash(make_runner(DiesBeforeSending(spool(config))))
    assert journal(config).latest(DAY).phase == "intent"

    healthy = SimulatedPrinter(spool(config))
    for _ in range(3):
        assert make_runner(healthy).run() == EXIT_UNKNOWN
    assert state(config).status == UNKNOWN
    assert healthy._load() == {}
    assert "not retrying automatically" in alert_file.read_text()


def test_crash_right_after_sending_recovers_the_job_from_the_queue(config, make_runner):
    crash(make_runner(DiesAfterSending(spool(config), ticks=2)))
    assert journal(config).latest(DAY).job_id is None

    healthy = SimulatedPrinter(spool(config), ticks=2)
    assert make_runner(healthy).run() == EXIT_OK
    assert state(config).status == OK
    assert state(config).job_id == "sim-1"
    assert len(healthy._load()) == 1


def test_crash_after_sending_with_job_already_gone_is_unknown(config, make_runner):
    crash(make_runner(DiesAfterSending(spool(config), ticks=2)))
    mark_job_done(config)
    healthy = SimulatedPrinter(spool(config))
    assert make_runner(healthy).run() == EXIT_UNKNOWN
    assert len(healthy._load()) == 1


def test_reboot_with_unknown_state_never_prints_again(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config))).run()
    mark_job_done(config)
    assert state(config).status == UNKNOWN
    for _ in range(3):
        printer = SimulatedPrinter(spool(config))
        make_runner(printer).run()
        assert len(printer._load()) == 1
    assert state(config).status == UNKNOWN


def test_unknown_job_still_in_queue_is_confirmed_when_it_finishes(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config), ticks=2)).run()
    assert state(config).status == UNKNOWN
    printer = SimulatedPrinter(spool(config), ticks=2)
    assert make_runner(printer).run() == EXIT_OK
    assert state(config).status == OK
    assert len(printer._load()) == 1


def test_spooler_down_during_recovery_keeps_unknown_then_resumes(config, make_runner):
    class SpoolerGone(SimulatedPrinter):
        def status(self, job_id):
            raise QueueUnreadable("spooler stopped")

    make_runner(SpoolerGone(spool(config))).run()
    assert state(config).status == SENT

    down = SimulatedPrinter(spool(config), unreadable=True)
    assert make_runner(down).run() == EXIT_UNKNOWN
    assert state(config).status == UNKNOWN
    assert make_runner(down).run() == EXIT_UNKNOWN

    back = SimulatedPrinter(spool(config))
    assert make_runner(back).run() == EXIT_OK
    assert len(back._load()) == 1


def test_spooler_down_while_recovering_an_unlinked_attempt_stays_unknown(config, make_runner):
    crash(make_runner(DiesAfterSending(spool(config), ticks=2)))
    down = SimulatedPrinter(spool(config), unreadable=True)
    assert make_runner(down).run() == EXIT_UNKNOWN
    up = SimulatedPrinter(spool(config), ticks=2)
    assert make_runner(up).run() == EXIT_OK
    assert len(up._load()) == 1


def test_failed_cancel_is_unknown_not_a_reason_to_reprint(config, make_runner):
    class CannotCancel(SimulatedPrinter):
        def cancel(self, job_id):
            raise PrinterError("access denied")

    stuck = CannotCancel(spool(config), stuck=True)
    assert make_runner(stuck).run() == EXIT_UNKNOWN
    assert state(config).status == UNKNOWN
    assert make_runner(stuck).run() == EXIT_UNKNOWN
    assert len(stuck._load()) == 1


def test_rejected_submit_is_a_plain_failure_and_can_be_retried(config, make_runner):
    pdf_gone = SimulatedPrinter(spool(config), unreadable=True)
    assert make_runner(pdf_gone).run() == EXIT_FAILED
    assert state(config).status == FAILED
    healthy = SimulatedPrinter(spool(config))
    assert make_runner(healthy).run() == EXIT_OK


def test_resolve_printed_closes_the_day(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config))).run()
    assert make_runner(SimulatedPrinter(spool(config))).resolve(printed=True) == EXIT_OK
    assert state(config).status == OK
    assert journal(config).latest(DAY).phase == "confirmed"


def test_resolve_not_printed_allows_exactly_one_reprint(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config), ticks=9)).run()
    printer = SimulatedPrinter(spool(config))
    assert make_runner(printer).resolve(printed=False) == EXIT_OK
    assert state(config).status == FAILED
    assert make_runner(printer).run() == EXIT_OK
    assert make_runner(printer).run() == EXIT_OK
    assert printer.printed_jobs() == ["sim-2"]


def test_resolve_without_an_open_attempt_does_nothing(config, make_runner):
    make_runner().run()
    assert make_runner().resolve(printed=False) == EXIT_FAILED
    assert state(config).status == OK


def test_print_only_refuses_while_an_attempt_is_unresolved(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config))).run()
    printer = SimulatedPrinter(spool(config))
    assert make_runner(printer).print_only() == EXIT_UNKNOWN
    assert len(printer._load()) == 1


def test_check_reports_unknown_with_its_own_exit_code(config, make_runner):
    make_runner(AmbiguousSubmit(spool(config))).run()
    assert make_runner().check() == EXIT_UNKNOWN


def test_check_reports_an_in_flight_attempt_as_pending(config, make_runner):
    crash(make_runner(DiesBeforeSending(spool(config))))
    assert make_runner().check() == EXIT_PENDING


def test_journal_wins_when_the_state_file_was_not_updated(config, make_runner):
    make_runner(SimulatedPrinter(spool(config))).run()
    stale = state(config)
    stale.status = SENT
    StateStore(config.state_dir).save(stale)
    printer = SimulatedPrinter(spool(config))
    assert make_runner(printer).run() == EXIT_OK
    assert state(config).status == OK
    assert len(printer._load()) == 1


def test_state_file_from_version_0_1_is_picked_up(config, make_runner):
    make_runner(SimulatedPrinter(spool(config), ticks=2)).run()
    path = StateStore(config.state_dir).path(DAY)
    data = json.loads(path.read_text())
    data["status"] = "enviado"
    path.write_text(json.dumps(data))
    (config.state_dir / "journal.db").unlink()
    path_spool = spool(config) / "spool.json"
    jobs = json.loads(path_spool.read_text())
    jobs["sim-1"]["state"] = "queued"
    jobs["sim-1"]["polls"] = 0
    path_spool.write_text(json.dumps(jobs))
    printer = SimulatedPrinter(spool(config), ticks=2)
    assert make_runner(printer).run() == EXIT_OK
    assert len(printer._load()) == 1


def test_repeated_identical_alerts_are_written_once(config, make_runner, alert_file):
    make_runner(AmbiguousSubmit(spool(config))).run()
    mark_job_done(config)
    for _ in range(4):
        make_runner(SimulatedPrinter(spool(config))).run()
    assert len(alert_file.read_text().splitlines()) == 2


def test_journal_numbers_attempts_per_day(tmp_path):
    db = Journal(tmp_path / "j.db")
    first = db.begin(DAY, "a.pdf", ["1"])
    db.set_phase(first.id, "cancelled")
    second = db.begin(DAY, "a.pdf", [])
    assert (first.seq, second.seq) == (1, 2)
    assert db.latest(DAY).id == second.id
    assert db.latest(DAY).baseline == ()
    assert db.latest("2026-03-11") is None


def test_cli_resolve_and_unknown_exit_codes(tmp_path):
    work = ["--workdir", str(tmp_path)]
    main(["seed", *work])
    assert main(["resolve", *work, "--printed"]) == EXIT_FAILED
    assert main(["run", *work]) == EXIT_OK
    assert main(["check", *work]) == EXIT_OK


def yesterday_unknown(config, make_runner):
    earlier = datetime(2026, 3, 9, 8, 0, 0)
    make_runner(AmbiguousSubmit(spool(config)), now=earlier).run()
    mark_job_done(config)
    return earlier.date().isoformat()


def test_unresolved_attempt_from_an_earlier_day_is_reported_today(config, make_runner, alert_file):
    old_day = yesterday_unknown(config, make_runner)
    printer = SimulatedPrinter(spool(config))
    assert make_runner(printer).run() == EXIT_OK
    assert f"unresolved attempt from {old_day} (unknown)" in alert_file.read_text()
    assert len(printer._load()) == 2


def test_check_also_reports_an_old_unresolved_attempt_when_today_is_ok(
    config, make_runner, alert_file
):
    old_day = yesterday_unknown(config, make_runner)
    make_runner(SimulatedPrinter(spool(config))).run()
    alert_file.unlink()
    assert make_runner().check() == EXIT_OK
    assert f"unresolved attempt from {old_day}" in alert_file.read_text()


def test_resolve_can_settle_an_earlier_day(config, make_runner, alert_file):
    old_day = yesterday_unknown(config, make_runner)
    assert make_runner().resolve(printed=True, day=old_day) == EXIT_OK
    make_runner(SimulatedPrinter(spool(config))).run()
    assert not alert_file.exists() or "unresolved attempt" not in alert_file.read_text()
    assert StateStore(config.state_dir).load(old_day).status == OK


def test_alerts_do_not_pile_up_when_two_unresolved_days_alternate(config, make_runner, alert_file):
    yesterday_unknown(config, make_runner)
    make_runner(AmbiguousSubmit(spool(config))).run()
    mark_job_done(config)
    for _ in range(6):
        make_runner(SimulatedPrinter(spool(config))).run()
    lines = alert_file.read_text().splitlines()
    assert len(lines) == len(set(line.split("] ", 1)[1] for line in lines))
