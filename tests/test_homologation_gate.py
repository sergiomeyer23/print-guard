import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_homologation", ROOT / "scripts" / "check_homologation.py"
)
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

TEMPLATE = """
| Field | Value |
|---|---|
| Version | {version} |

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 1.1 | First | ok | {r1} | {e1} |
| 1.2 | Second | ok | {r2} | {e2} |

| Decision | Name | Date |
|---|---|---|
| {decision} | {name} | {date} |
"""


def filled(**overrides):
    values = dict(
        version="0.3.0",
        r1="PASS",
        e1="log line",
        r2="PASS",
        e2="photo",
        decision="Approved",
        name="Someone",
        date="2026-11-10",
    )
    values.update(overrides)
    return TEMPLATE.format(**values)


def test_a_complete_approved_checklist_passes():
    report = gate.evaluate(filled())
    assert report.approved
    assert (report.checks, report.passed) == (2, 2)


def test_blank_results_are_pending_not_assumed():
    report = gate.evaluate(filled(r1="", e1=""))
    assert not report.approved
    assert "1.1: no result" in report.pending


def test_a_pass_without_evidence_is_pending():
    report = gate.evaluate(filled(e2=""))
    assert not report.approved
    assert "1.2: PASS without evidence" in report.pending


def test_any_fail_blocks_approval_even_when_signed_off():
    report = gate.evaluate(filled(r2="FAIL"))
    assert report.failed == ["1.2"]
    assert not report.approved


def test_not_applicable_needs_a_reason():
    assert gate.evaluate(filled(r1="N/A", e1="")).pending
    assert gate.evaluate(filled(r1="N/A", e1="no PDF app on this machine")).approved


def test_missing_record_field_is_pending():
    assert "record: Version" in gate.evaluate(filled(version="")).pending


def test_decision_must_say_approved_and_be_signed():
    assert not gate.evaluate(filled(decision="Not approved")).approved
    assert not gate.evaluate(filled(name="")).approved
    assert not gate.evaluate(
        filled(decision="Approved for real use / approved with conditions")
    ).approved
    assert gate.evaluate(filled(decision="Approved with conditions")).approved


def test_the_committed_template_has_every_scenario_and_unique_ids():
    text = (ROOT / "docs" / "homologation-checklist.md").read_text(encoding="utf-8")
    ids = []
    for header, rows in gate.tables(text):
        if "Result" in header:
            ids += [row[0] for row in rows]
    assert len(ids) >= 40
    assert len(ids) == len(set(ids))
    for section in ("1.", "2.", "3.", "4.", "5.", "6.", "7."):
        assert any(i.startswith(section) for i in ids)
