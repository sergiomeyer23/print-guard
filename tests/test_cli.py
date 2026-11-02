from datetime import date
from pathlib import Path

from printguard.cli import main
from printguard.report import pdf_problem, render_pdf
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
