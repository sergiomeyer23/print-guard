"""Check a filled-in homologation checklist and list what is still missing.

Usage: python scripts/check_homologation.py [path]

Exits 0 only when every record field is filled, every check has a result and
evidence, nothing failed, and the sign-off says approved. Anything else exits 1.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

RESULTS = {"PASS", "FAIL", "N/A"}
DEFAULT = Path(__file__).resolve().parent.parent / "docs" / "homologation-checklist.md"


@dataclass
class Report:
    checks: int = 0
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    decision: str = ""

    @property
    def approved(self) -> bool:
        decision = self.decision.lower()
        return (
            not self.pending
            and not self.failed
            and decision.startswith("approved")
            and "not approved" not in decision
        )


def tables(text: str):
    block: list[list[str]] = []
    for line in text.splitlines() + [""]:
        if line.strip().startswith("|"):
            block.append([cell.strip() for cell in line.strip().strip("|").split("|")])
            continue
        if len(block) > 2:
            yield block[0], block[2:]
        block = []


def evaluate(text: str) -> Report:
    report = Report()
    for header, rows in tables(text):
        if header[:2] == ["Field", "Value"]:
            check_record(rows, report)
        elif "Result" in header and "Evidence" in header:
            check_results(header, rows, report)
        elif header[:3] == ["Decision", "Name", "Date"]:
            check_signoff(rows, report)
    if not report.decision:
        report.pending.append("sign-off: decision")
    return report


def check_record(rows: list[list[str]], report: Report) -> None:
    for row in rows:
        if len(row) < 2 or not row[1]:
            report.pending.append(f"record: {row[0]}")


def check_results(header: list[str], rows: list[list[str]], report: Report) -> None:
    result_at, evidence_at = header.index("Result"), header.index("Evidence")
    for row in rows:
        name = row[0]
        report.checks += 1
        result = row[result_at].upper() if len(row) > result_at else ""
        evidence = row[evidence_at] if len(row) > evidence_at else ""
        if result not in RESULTS:
            report.pending.append(f"{name}: no result")
        elif not evidence:
            report.pending.append(f"{name}: {result} without evidence")
        elif result == "FAIL":
            report.failed.append(name)
        elif result == "PASS":
            report.passed += 1


def check_signoff(rows: list[list[str]], report: Report) -> None:
    for row in rows:
        decision = row[0]
        if not decision or "/" in decision or len(row) < 3 or not row[1] or not row[2]:
            return
        report.decision = decision


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    report = evaluate(path.read_text(encoding="utf-8"))
    print(
        f"{path}: {report.checks} checks, {report.passed} passed, "
        f"{len(report.failed)} failed, {len(report.pending)} incomplete"
    )
    for name in report.failed:
        print(f"  FAILED   {name}")
    for item in report.pending:
        print(f"  MISSING  {item}")
    print("APPROVED" if report.approved else "NOT APPROVED: do not publish a stable release")
    return 0 if report.approved else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
