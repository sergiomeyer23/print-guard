import json

import pytest

from printguard.printers import (
    JobStatus,
    PrinterError,
    QueueUnreadable,
    SimulatedPrinter,
    SubmitRejected,
    WindowsSpoolerPrinter,
)
from printguard.printers.spooler import CommandTimeout, classify, parse_jobs, parse_queue, quote


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


def test_queue_exposes_status_and_document(printer, ps):
    ps.queue[4] = "Printing"
    entries = printer.queue()
    assert entries["4"].status is JobStatus.PRINTING


def test_start_process_failure_is_a_proven_rejection(printer, ps, tmp_path):
    def failing(script):
        if script.startswith("Start-Process"):
            raise PrinterError("file association missing")
        return ps(script)

    printer.powershell = failing
    with pytest.raises(SubmitRejected):
        printer.submit(tmp_path / "r.pdf")


def test_unreadable_queue_before_sending_is_a_proven_rejection(printer, ps, tmp_path):
    ps.fail_listing = True
    with pytest.raises(SubmitRejected):
        printer.submit(tmp_path / "r.pdf")


def test_timeout_while_sending_is_ambiguous(printer, ps, tmp_path):
    def slow(script):
        if script.startswith("Start-Process"):
            raise CommandTimeout("powershell timed out")
        return ps(script)

    printer.powershell = slow
    with pytest.raises(CommandTimeout) as caught:
        printer.submit(tmp_path / "r.pdf")
    assert not isinstance(caught.value, SubmitRejected)


def test_parse_queue_keeps_document_names():
    raw = '[{"ID":1,"Status":"Normal","Document":"report_2026-03-10.pdf"}]'
    assert parse_queue(raw) == {"1": ("Normal", "report_2026-03-10.pdf")}


@pytest.mark.parametrize("backend", [WindowsSpoolerPrinter, SimulatedPrinter])
def test_backends_implement_the_whole_printer_protocol(backend):
    for method in ("submit", "status", "cancel", "queue"):
        assert callable(getattr(backend, method))


def test_null_and_empty_array_mean_an_empty_queue():
    assert parse_queue("null") == {}
    assert parse_queue("[]") == {}


def test_script_is_passed_encoded_so_quoting_cannot_break_it(monkeypatch):
    import base64
    import subprocess

    from printguard.printers import spooler

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(spooler.subprocess, "run", fake_run)
    script = "Get-PrintJob -PrinterName 'Office \"A\"'"
    assert spooler.run_powershell(script) == "[]"
    argv = captured["argv"]
    assert "-Command" not in argv
    decoded = base64.b64decode(argv[argv.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert decoded.endswith(script)


def test_clixml_error_from_windows_powershell_is_flattened():
    from printguard.printers.spooler import clean_error

    raw = (
        '#< CLIXML\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<Obj S="progress" RefId="0"><MS><AV>Preparing modules for first use.</AV></MS></Obj>'
        '<S S="Error">Start-Process : This command cannot be run due to the error: No application '
        "is associated with the specified file for _x000D__x000A_</S>"
        '<S S="Error">this operation._x000D__x000A_</S>'
        '<S S="Error">At line:1 char:59_x000D__x000A_</S></Objs>'
    )
    message = clean_error(raw)
    assert message.startswith("Start-Process : This command cannot be run")
    assert "associated with the specified file for this operation." in message
    assert "CLIXML" not in message and "_x000D_" not in message


def test_plain_stderr_is_only_trimmed():
    from printguard.printers.spooler import clean_error

    assert clean_error("  boom \n") == "boom"
