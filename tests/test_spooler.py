import json

import pytest

from printguard.printers import JobStatus, PrinterError, QueueUnreadable, WindowsSpoolerPrinter
from printguard.printers.spooler import classify, parse_jobs, quote


class FakePowerShell:
    def __init__(self):
        self.queue: dict[int, str] = {}
        self.calls: list[str] = []
        self.fail_listing = False
        self.garbage = False
        self.add_job_on_print: int | None = 7

    def __call__(self, script: str) -> str:
        self.calls.append(script)
        if script.startswith("Get-PrintJob"):
            return self._list()
        if script.startswith("Start-Process") and self.add_job_on_print is not None:
            self.queue[self.add_job_on_print] = "Spooling"
        if script.startswith("Remove-PrintJob"):
            self.queue.pop(int(script.rsplit("-ID", 1)[1]), None)
        return ""

    def _list(self) -> str:
        if self.fail_listing:
            raise PrinterError("RPC server unavailable")
        if self.garbage:
            return "<<not json>>"
        items = [{"ID": k, "Status": v} for k, v in self.queue.items()]
        if not items:
            return ""
        return json.dumps(items[0] if len(items) == 1 else items)


@pytest.fixture
def ps():
    return FakePowerShell()


@pytest.fixture
def printer(ps):
    return WindowsSpoolerPrinter("Office 'A'", powershell=ps, sleep=lambda _: None)


def test_submit_returns_the_new_job_id(printer, ps, tmp_path):
    ps.queue[3] = "Printing"
    assert printer.submit(tmp_path / "r.pdf") == "7"


def test_submit_fails_when_no_job_shows_up(printer, ps, tmp_path):
    ps.add_job_on_print = None
    with pytest.raises(PrinterError, match="no new job"):
        printer.submit(tmp_path / "r.pdf")


def test_job_leaving_the_queue_counts_as_done(printer, ps):
    ps.queue[7] = "Printing"
    assert printer.status("7") is JobStatus.PRINTING
    del ps.queue[7]
    assert printer.status("7") is JobStatus.DONE


def test_error_flags_are_reported_as_error(printer, ps):
    ps.queue[7] = "Error, Offline"
    assert printer.status("7") is JobStatus.ERROR


def test_unreadable_queue_raises(printer, ps):
    ps.fail_listing = True
    with pytest.raises(QueueUnreadable):
        printer.status("7")


def test_garbage_output_raises(printer, ps):
    ps.garbage = True
    with pytest.raises(QueueUnreadable):
        printer.status("7")


def test_cancel_removes_the_job(printer, ps):
    ps.queue[7] = "Spooling"
    printer.cancel("7")
    assert 7 not in ps.queue


def test_printer_name_is_quoted(printer, ps, tmp_path):
    printer.submit(tmp_path / "r.pdf")
    assert "Office ''A''" in ps.calls[0]
    assert quote("it's") == "'it''s'"


def test_parse_single_object_and_list():
    assert parse_jobs('{"ID":1,"Status":"Normal"}') == {"1": "Normal"}
    assert parse_jobs('[{"ID":1,"Status":"a"},{"ID":2,"Status":"b"}]') == {"1": "a", "2": "b"}
    assert parse_jobs("") == {}


def test_classify_defaults_to_queued():
    assert classify("Normal") is JobStatus.QUEUED
    assert classify("Printed") is JobStatus.DONE
