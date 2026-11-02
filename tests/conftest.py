from datetime import date, datetime
from pathlib import Path

import pytest

from printguard.alerts import Alerter
from printguard.printers import SimulatedPrinter
from printguard.runner import Config, Runner
from printguard.source import seed

NOW = datetime(2026, 3, 10, 8, 0, 0)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    db = tmp_path / "data" / "demo.db"
    seed(db, date(2026, 3, 10))
    return Config(
        db_path=db,
        state_dir=tmp_path / "state",
        out_dir=tmp_path / "out",
        alert_dir=tmp_path / "out",
        confirm_timeout=6.0,
        poll_interval=2.0,
    )


@pytest.fixture
def make_runner(config: Config):
    def build(printer=None, now=NOW, **overrides) -> Runner:
        printer = printer or SimulatedPrinter(config.out_dir / "spool")
        return Runner(
            config,
            printer,
            Alerter(config.alert_dir),
            now=lambda: now,
            sleep=lambda _: None,
            **overrides,
        )

    return build


@pytest.fixture
def alert_file(config: Config) -> Path:
    return config.alert_dir / "ALERTA_2026-03-10.txt"
