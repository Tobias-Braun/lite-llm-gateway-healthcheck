"""Wall-clock time grid shared by every history timeline.

Histories are not reported per stored round but on fixed slots of `check_interval_seconds`
ending at request time, so every family and model gets the same number of points at the same
times, and a slot without a check stays visible as `unknown`.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db import CheckResult


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Slot:
    """The half-open window `(start, end]`, as ISO strings comparable with stored `round_at` values."""

    start: str
    end: str


def grid(interval_seconds: float, count: int, now: datetime | None = None) -> list[Slot]:
    """The last `count` slots of `interval_seconds` ending at `now`, oldest first."""
    end = (now or datetime.now(UTC)).replace(microsecond=0)
    interval = timedelta(seconds=interval_seconds)
    return [Slot(_iso(end - (i + 1) * interval), _iso(end - i * interval)) for i in reversed(range(count))]


def latest_per_slot(slots: list[Slot], checks: list[CheckResult]) -> list[dict[str, CheckResult]]:
    """Per slot, the latest check of each model that landed in it, keyed by model name.

    `checks` must be ordered oldest first, so a later check of the same model in a slot wins.
    """
    ends = [slot.end for slot in slots]
    buckets: list[dict[str, CheckResult]] = [{} for _ in slots]
    for check in checks:
        index = bisect_left(ends, check.round_at)
        if index < len(slots) and check.round_at > slots[index].start:
            buckets[index][check.model] = check
    return buckets
