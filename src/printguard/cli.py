from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, time
from pathlib import Path

from printguard.alerts import Alerter
from printguard.printers import Printer, SimulatedPrinter, WindowsSpoolerPrinter
from printguard.runner import Config, Runner
from printguard.source import seed


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workdir", type=Path, default=Path("."))
    common.add_argument("--db", type=Path, help="SQLite file (default: <workdir>/data/demo.db)")
    common.add_argument("--printer", choices=["simulated", "spooler"], default="simulated")
    common.add_argument(
        "--printer-name", default="", help="Windows printer name for --printer spooler"
    )
    common.add_argument(
        "--sim-fail",
        choices=["stuck", "unreadable"],
        help="inject a fault into the simulated printer",
    )
    common.add_argument("--confirm-timeout", type=float, default=120.0)
    common.add_argument(
        "--event-log", action="store_true", help="also write to the Windows Event Log"
    )

    parser = argparse.ArgumentParser(prog="printguard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", parents=[common], help="create the demo database").add_argument(
        "--force", action="store_true"
    )
    sub.add_parser("run", parents=[common], help="query, render, print and confirm")
    sub.add_parser("print-only", parents=[common], help="reprint today's PDF without querying")
    sub.add_parser("check", parents=[common], help="report today's state").add_argument(
        "--deadline", type=parse_clock, help="HH:MM, raise an alert if not ok by then"
    )
    return parser


def parse_clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def make_printer(args: argparse.Namespace, workdir: Path) -> Printer:
    if args.printer == "spooler":
        if not args.printer_name:
            raise SystemExit("--printer-name is required with --printer spooler")
        return WindowsSpoolerPrinter(args.printer_name)
    return SimulatedPrinter(
        workdir / "out" / "spool",
        stuck=args.sim_fail == "stuck",
        unreadable=args.sim_fail == "unreadable",
    )


def make_runner(args: argparse.Namespace) -> Runner:
    workdir = args.workdir
    config = Config(
        db_path=args.db or workdir / "data" / "demo.db",
        state_dir=workdir / "state",
        out_dir=workdir / "out",
        alert_dir=workdir / "out",
        confirm_timeout=args.confirm_timeout,
    )
    alerter = Alerter(config.alert_dir, event_log=args.event_log)
    return Runner(config, make_printer(args, workdir), alerter)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        db = args.db or args.workdir / "data" / "demo.db"
        try:
            count = seed(db, datetime.now().date(), force=args.force)
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"seeded {count} rows into {db}")
        return 0
    runner = make_runner(args)
    if args.command == "run":
        return runner.run()
    if args.command == "print-only":
        return runner.print_only()
    return runner.check(args.deadline)
