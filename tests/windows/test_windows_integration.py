import os
import sys
import time
from datetime import datetime

import pytest

from printguard.alerts import Alerter
from printguard.journal import Journal
from printguard.printers import JobStatus, PrinterError, QueueUnreadable, WindowsSpoolerPrinter
from printguard.printers.spooler import quote, run_powershell
from printguard.runner import EXIT_FAILED, EXIT_UNKNOWN, Config, Runner
from printguard.state import FAILED, UNKNOWN, StateStore

PRINTER = os.environ.get("PRINTGUARD_TEST_PRINTER", "")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not PRINTER,
    reason="needs Windows and a paused test printer (PRINTGUARD_TEST_PRINTER)",
)


@pytest.fixture(autouse=True)
def clean_queue():
    clear = f"Get-PrintJob -PrinterName {quote(PRINTER)} | Remove-PrintJob"
    run_powershell(clear)
    yield
    run_powershell(clear)


@pytest.fixture
def printer():
    return WindowsSpoolerPrinter(PRINTER)


def add_job(printer):
    before = set(printer.queue())
    run_powershell(f"'printguard integration test' | Out-Printer -Name {quote(PRINTER)}")
    for _ in range(20):
        new = set(printer.queue()) - before
        if new:
            return new.pop()
        time.sleep(0.5)
    raise AssertionError("Out-Printer did not leave a job in the queue")


def test_empty_queue_reads_as_empty(printer):
    assert printer.queue() == {}


def test_job_is_visible_then_cancellable(printer):
    job_id = add_job(printer)
    assert job_id in printer.queue()
    assert printer.status(job_id) in (JobStatus.QUEUED, JobStatus.PRINTING)
    printer.cancel(job_id)
    assert job_id not in printer.queue()
    assert printer.status(job_id) is JobStatus.DONE


def test_cancelling_a_missing_job_is_an_error(printer):
    with pytest.raises(PrinterError):
        printer.cancel("987654")


def test_unknown_printer_name_reads_as_unreadable_queue():
    with pytest.raises(QueueUnreadable):
        WindowsSpoolerPrinter("printguard-no-such-printer").queue()


def test_submit_through_printto_finds_the_new_job(printer, tmp_path):
    document = tmp_path / "printguard-sample.txt"
    document.write_text("printguard integration test")
    job_id = printer.submit(document)
    entry = printer.queue()[job_id]
    assert "printguard-sample" in entry.document
    printer.cancel(job_id)


def make_runner(tmp_path):
    config = Config(
        db_path=tmp_path / "unused.db",
        state_dir=tmp_path / "state",
        out_dir=tmp_path / "out",
        alert_dir=tmp_path / "out",
        confirm_timeout=2.0,
        poll_interval=1.0,
    )
    runner = Runner(config, WindowsSpoolerPrinter(PRINTER), Alerter(config.alert_dir))
    return config, runner


def open_attempt(config, job_id):
    day = datetime.now().date().isoformat()
    journal = Journal(config.state_dir / "journal.db")
    attempt = journal.begin(day, str(config.out_dir / f"report_{day}.pdf"), [])
    journal.set_job(attempt.id, job_id)
    return day


def test_stuck_job_on_a_real_spooler_is_cancelled(printer, tmp_path):
    job_id = add_job(printer)
    config, runner = make_runner(tmp_path)
    day = open_attempt(config, job_id)
    assert runner.run() == EXIT_FAILED
    assert StateStore(config.state_dir).load(day).status == FAILED
    assert printer.queue() == {}


def test_vanished_job_on_a_real_spooler_is_unknown(tmp_path):
    config, runner = make_runner(tmp_path)
    day = open_attempt(config, "987654")
    assert runner.run() == EXIT_UNKNOWN
    assert StateStore(config.state_dir).load(day).status == UNKNOWN
