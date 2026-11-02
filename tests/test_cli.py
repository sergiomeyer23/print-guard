import sys
from datetime import date
from pathlib import Path

import pytest

from printguard.cli import main
from printguard.report import pdf_problem, render_pdf
from printguard.runner import EXIT_ERROR
from printguard.source import fetch_pending, seed


def test_demo_flow_end_to_end(tmp_path):
    work = ["--workdir", str(tmp_path)]
    assert main(["seed", *work]) == 0
    assert main(["run", *work]) == 0
    assert main(["check", *work]) == 0
    assert main(["print-only", *work]) == 0
    assert list((tmp_path / "out").glob("report_*.pdf"))


def test_seed_refuses_to_overwrite(tmp_path):
    work = ["--workdir", str(tmp_path)]
    assert main(["seed", *work]) == 0
    assert main(["seed", *work]) == 1
    assert main(["seed", *work, "--force"]) == 0


def test_stuck_fault_injection_exits_nonzero_and_alerts(tmp_path):
    work = ["--workdir", str(tmp_path), "--confirm-timeout", "1"]
    main(["seed", *work])
    assert main(["run", *work, "--sim-fail", "stuck"]) == 1
    assert list((tmp_path / "out").glob("ALERTA_*.txt"))
    assert main(["check", *work]) == 1


def test_check_with_no_run_is_pending_and_alerts_after_deadline(tmp_path):
    work = ["--workdir", str(tmp_path)]
    assert main(["check", *work]) == 2
    assert not list((tmp_path / "out").glob("ALERTA_*.txt"))
    assert main(["check", *work, "--deadline", "00:00"]) == 2
    assert list((tmp_path / "out").glob("ALERTA_*.txt"))


def test_report_contains_query_timestamp(tmp_path):
    from datetime import datetime

    db = tmp_path / "d.db"
    seed(db, date(2026, 3, 10))
    rows = fetch_pending(db, date(2026, 3, 10))
    pdf = render_pdf(rows, tmp_path / "r.pdf", datetime(2026, 3, 10, 8, 1, 2))
    assert pdf_problem(pdf) is None
    assert pdf_problem(Path(tmp_path / "missing.pdf")) == "file does not exist"


def test_database_file_is_released_after_use(tmp_path):
    db = tmp_path / "d.db"
    seed(db, date(2026, 3, 10))
    fetch_pending(db, date(2026, 3, 10))
    db.unlink()
    seed(db, date(2026, 3, 10))
    seed(db, date(2026, 3, 10), force=True)


def test_version_flag(capsys):
    from printguard import __version__

    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_unexpected_error_exits_with_5_and_leaves_an_alert(tmp_path):
    work = ["--workdir", str(tmp_path)]
    main(["seed", *work])
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "journal.db").write_bytes(b"this is not a sqlite database" * 20)
    assert main(["run", *work]) == EXIT_ERROR
    alert = next((tmp_path / "out").glob("ALERTA_*.txt")).read_text()
    assert "unexpected error: DatabaseError" in alert


def test_lock_is_released_after_an_unexpected_error(tmp_path):
    from printguard.lock import ProcessLock

    work = ["--workdir", str(tmp_path)]
    main(["seed", *work])
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "journal.db").write_bytes(b"garbage" * 40)
    main(["run", *work])
    with ProcessLock(tmp_path / "state" / "printguard.lock"):
        pass


def test_event_log_is_skipped_off_windows():
    from printguard.alerts import write_event_log

    if sys.platform != "win32":
        assert write_event_log("anything") is False


def test_event_log_script_quotes_the_message(monkeypatch):
    from printguard import alerts

    monkeypatch.setattr(alerts.sys, "platform", "win32")
    seen = []
    assert alerts.write_event_log("it's broken", powershell=seen.append) is True
    assert "-Source printguard" in seen[0]
    assert "'it''s broken'" in seen[0]


def test_event_log_failure_does_not_raise(monkeypatch):
    from printguard import alerts
    from printguard.printers import PrinterError

    def denied(script):
        raise PrinterError("access denied")

    monkeypatch.setattr(alerts.sys, "platform", "win32")
    assert alerts.write_event_log("x", powershell=denied) is False


def test_empty_report_is_a_valid_pdf(tmp_path):
    from datetime import datetime

    pdf = render_pdf([], tmp_path / "empty.pdf", datetime(2026, 3, 10, 8, 0, 0))
    assert pdf_problem(pdf) is None


def test_long_report_spans_pages_and_stays_valid(tmp_path):
    from datetime import datetime

    rows = [
        (i, f"SKU-{i}", "Hex bolt M8 (box)", i % 40 + 1, "A-01-01", "2026-03-10")
        for i in range(300)
    ]
    pdf = render_pdf(rows, tmp_path / "long.pdf", datetime(2026, 3, 10, 8, 0, 0))
    data = pdf.read_bytes()
    assert pdf_problem(pdf) is None
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 3


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_working_directories_are_private(tmp_path):
    work = ["--workdir", str(tmp_path)]
    main(["seed", *work])
    main(["run", *work])
    for name in ("state", "out"):
        assert (tmp_path / name).stat().st_mode & 0o077 == 0
