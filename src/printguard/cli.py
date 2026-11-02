from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, time
from pathlib import Path

from printguard import __version__
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
    common.add_argument("--poll-interval", type=float, default=2.0)
    common.add_argument(
        "--sim-ticks", type=int, default=1, help="polls before a simulated job finishes"
    )
    common.add_argument(
        "--event-log", action="store_true", help="also write to the Windows Event Log"
    )

    parser = argparse.ArgumentParser(prog="printguard", description=__doc__)
    parser.add_argument("--version", action="version", version=f"printguard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", parents=[common], help="create the demo database").add_argument(
        "--force", action="store_true"
    )
    sub.add_parser("run", parents=[common], help="query, render, print and confirm")
    sub.add_parser("print-only", parents=[common], help="reprint today's PDF without querying")
    sub.add_parser("check", parents=[common], help="report today's state").add_argument(
        "--deadline", type=parse_clock, help="HH:MM, raise an alert if not ok by then"
    )
    resolve = sub.add_parser("resolve", parents=[common], help="settle an unknown attempt by hand")
    outcome = resolve.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--printed", action="store_true", help="the paper came out")
    outcome.add_argument("--not-printed", action="store_true", help="it did not, allow a reprint")
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
        ticks=args.sim_ticks,
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
        poll_interval=args.poll_interval,
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
    try:
        return dispatch(runner, args)
    except Exception as exc:
        return runner.report_unexpected(exc)


def dispatch(runner: Runner, args: argparse.Namespace) -> int:
    if args.command == "run":
        return runner.run()
    if args.command == "print-only":
        return runner.print_only()
    if args.command == "resolve":
        return runner.resolve(printed=args.printed)
    return runner.check(args.deadline)
