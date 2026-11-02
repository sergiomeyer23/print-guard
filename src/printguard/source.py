from __future__ import annotations

import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

COLUMNS = ("id", "sku", "description", "qty", "location", "due_date")

SCHEMA = """
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    description TEXT NOT NULL,
    qty INTEGER NOT NULL,
    location TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

PRODUCTS = [
    ("Copper fitting 15mm", "CF-015"),
    ("Steel bracket L", "SB-210"),
    ("Hex bolt M8 (box)", "HB-008"),
    ("PVC elbow 90", "PE-090"),
    ("Cable tie 300mm", "CT-300"),
    ("Pallet wrap roll", "PW-001"),
    ("Door hinge pair", "DH-044"),
    ("LED strip 5m", "LS-005"),
]


def seed(db_path: Path, today: date, rows: int = 60, force: bool = False) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and not force:
        raise FileExistsError(f"{db_path} already exists, pass --force to rebuild it")
    db_path.unlink(missing_ok=True)
    rng = random.Random(42)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(SCHEMA)
        conn.executemany(
            "INSERT INTO shipments (sku, description, qty, location, due_date, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [_fake_row(rng, today) for _ in range(rows)],
        )
    return rows


def _fake_row(rng: random.Random, today: date) -> tuple:
    description, sku = rng.choice(PRODUCTS)
    location = f"{rng.choice('ABCD')}-{rng.randint(1, 12):02d}-{rng.randint(1, 6):02d}"
    due = today + timedelta(days=rng.randint(-3, 4))
    status = rng.choice(["pending", "pending", "pending", "shipped"])
    return (sku, description, rng.randint(1, 40), location, due.isoformat(), status)


def fetch_pending(db_path: Path, today: date) -> list[tuple]:
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM shipments "
            "WHERE status = 'pending' AND due_date <= ? ORDER BY due_date, location",
            (today.isoformat(),),
        )
        return cursor.fetchall()
