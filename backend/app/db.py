"""SQLite storage for check results.

Every model check is one row in `checks`. All rows written by the same check round share
`round_id` and `round_at`, which lets the history be aggregated per round and family.
Connections are short-lived (one per operation) so they can be used from any thread.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    round_at TEXT NOT NULL,
    family TEXT NOT NULL,
    model TEXT NOT NULL,
    success INTEGER NOT NULL,
    latency_ms INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_family_round ON checks (family, round_at);
CREATE INDEX IF NOT EXISTS idx_checks_family_model ON checks (family, model, id);
"""


@dataclass
class CheckResult:
    round_id: str
    round_at: str
    family: str
    model: str
    success: bool
    latency_ms: int | None
    error: str | None


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path) -> None:
    """Create the database file, its parent directory and the schema if missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn, conn:
        conn.executescript(SCHEMA)


def insert_results(path: Path, results: list[CheckResult]) -> None:
    with closing(connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO checks (round_id, round_at, family, model, success, latency_ms, error)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (r.round_id, r.round_at, r.family, r.model, int(r.success), r.latency_ms, r.error)
                for r in results
            ],
        )


def _placeholders(values: list[str]) -> str:
    return ",".join("?" * len(values))


def latest_results(path: Path, family: str, models: list[str]) -> dict[str, CheckResult]:
    """Return the most recent result per model of a family, keyed by model name."""
    if not models:
        return {}
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT * FROM checks WHERE id IN ("
            f" SELECT MAX(id) FROM checks WHERE family = ? AND model IN ({_placeholders(models)})"
            " GROUP BY model)",
            [family, *models],
        ).fetchall()
    return {
        row["model"]: CheckResult(
            round_id=row["round_id"],
            round_at=row["round_at"],
            family=row["family"],
            model=row["model"],
            success=bool(row["success"]),
            latency_ms=row["latency_ms"],
            error=row["error"],
        )
        for row in rows
    }


def recent_rounds(path: Path, family: str, models: list[str], limit: int) -> list[tuple[str, bool]]:
    """Return `(round_at, all_succeeded)` for the last `limit` rounds of a family, oldest first.

    Only results of the currently configured models count, so models removed from the
    configuration no longer influence the family's availability.
    """
    if not models or limit <= 0:
        return []
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT round_at, MIN(success) AS all_ok FROM checks"
            f" WHERE family = ? AND model IN ({_placeholders(models)})"
            " GROUP BY round_id, round_at ORDER BY round_at DESC, round_id DESC LIMIT ?",
            [family, *models, limit],
        ).fetchall()
    return [(row["round_at"], bool(row["all_ok"])) for row in reversed(rows)]
