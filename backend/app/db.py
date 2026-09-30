"""SQLite storage for check results and the model list.

Every model check is one row in `checks`. All rows written by the same check round share
`round_id` and `round_at`, which lets the history be aggregated per round and family.
`models` holds the model list fetched from the gateway; models that disappeared from it are kept
with `active = 0`, so their check history stays but they are no longer checked or shown.
Connections are short-lived (one per operation) so they can be used from any thread.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from app.config import ModelDef, ModelFamily

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
CREATE TABLE IF NOT EXISTS models (
    model TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    provider TEXT NOT NULL,
    company TEXT NOT NULL,
    position INTEGER NOT NULL,
    active INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
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


def model_history_bounds(path: Path, family: str, model: str) -> tuple[int, str | None]:
    """Return `(stored round count, oldest round_at)` for one model; `oldest_at` is `None` if empty."""
    with closing(connect(path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count, MIN(round_at) AS oldest FROM checks WHERE family = ? AND model = ?",
            [family, model],
        ).fetchone()
    return row["count"], row["oldest"]


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


def recent_rounds(path: Path, family: str, models: list[str], limit: int) -> list[tuple[str, int, int]]:
    """Return `(round_at, succeeded, total)` for the last `limit` rounds of a family, oldest first.

    `total` is how many of the given (active) models reported in that round, so models that
    became inactive no longer influence the family's availability.
    """
    if not models or limit <= 0:
        return []
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT round_at, SUM(success) AS succeeded, COUNT(*) AS total FROM checks"
            f" WHERE family = ? AND model IN ({_placeholders(models)})"
            " GROUP BY round_id, round_at ORDER BY round_at DESC, round_id DESC LIMIT ?",
            [family, *models, limit],
        ).fetchall()
    return [(row["round_at"], row["succeeded"], row["total"]) for row in reversed(rows)]


def family_latency_rounds(
    path: Path, family: str, models: list[str], limit: int
) -> list[tuple[str, int, int, float | None]]:
    """Like `recent_rounds`, plus the mean latency of the round's successful checks (`None` if none succeeded)."""
    if not models or limit <= 0:
        return []
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT round_at, SUM(success) AS succeeded, COUNT(*) AS total,"
            " AVG(CASE WHEN success = 1 THEN latency_ms END) AS latency FROM checks"
            f" WHERE family = ? AND model IN ({_placeholders(models)})"
            " GROUP BY round_id, round_at ORDER BY round_at DESC, round_id DESC LIMIT ?",
            [family, *models, limit],
        ).fetchall()
    return [(row["round_at"], row["succeeded"], row["total"], row["latency"]) for row in reversed(rows)]


def latency_checks(path: Path, family: str, models: list[str], since: str) -> list[tuple[str, int]]:
    """Return `(round_at, latency_ms)` of every successful check of the given models at or after `since`."""
    if not models:
        return []
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT round_at, latency_ms FROM checks"
            f" WHERE family = ? AND model IN ({_placeholders(models)})"
            " AND success = 1 AND latency_ms IS NOT NULL AND round_at >= ?",
            [family, *models, since],
        ).fetchall()
    return [(row["round_at"], row["latency_ms"]) for row in rows]


def model_recent_rounds(path: Path, family: str, model: str, limit: int) -> list[tuple[str, bool, int | None, str | None]]:
    """Return `(round_at, success, latency_ms, error)` for the last `limit` rounds of a model, oldest first."""
    if limit <= 0:
        return []
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT round_at, success, latency_ms, error FROM checks WHERE family = ? AND model = ?"
            " ORDER BY round_at DESC, id DESC LIMIT ?",
            [family, model, limit],
        ).fetchall()
    return [(row["round_at"], bool(row["success"]), row["latency_ms"], row["error"]) for row in reversed(rows)]


def replace_models(path: Path, families: list[ModelFamily]) -> None:
    """Store `families` as the active model list, in order; every other stored model becomes inactive."""
    rows = [
        (model.modelname, family.title, model.provider, model.company, position)
        for position, (family, model) in enumerate((f, m) for f in families for m in f.models)
    ]
    with closing(connect(path)) as conn, conn:
        conn.execute("UPDATE models SET active = 0")
        conn.executemany(
            "INSERT INTO models (model, family, provider, company, position, active, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            " ON CONFLICT (model) DO UPDATE SET family = excluded.family, provider = excluded.provider,"
            " company = excluded.company, position = excluded.position, active = 1, updated_at = excluded.updated_at",
            rows,
        )


def active_models(path: Path) -> list[ModelFamily]:
    """Return the active models grouped into families, in stored order."""
    with closing(connect(path)) as conn:
        rows = conn.execute("SELECT * FROM models WHERE active = 1 ORDER BY position").fetchall()
    families: dict[str, list[ModelDef]] = {}
    for row in rows:
        families.setdefault(row["family"], []).append(
            ModelDef(modelname=row["model"], provider=row["provider"], company=row["company"])
        )
    return [ModelFamily(title=title, models=models) for title, models in families.items()]
