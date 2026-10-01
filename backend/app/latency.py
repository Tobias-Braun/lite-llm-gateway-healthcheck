"""Latency series for the `GET /api/latency` response: live rounds or time-of-day/week/month aggregates."""

import math
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app import db, slots
from app.config import Settings
from app.status import ApiModel, Availability, _family_availability, _model_availability

Span = Literal["live", "hour", "weekday", "monthday"]

# Every bucket of an aggregate span, so charts get a complete axis even where no check landed.
BUCKETS: dict[str, range] = {"hour": range(24), "weekday": range(7), "monthday": range(1, 32)}


class NotFoundError(LookupError):
    """The requested family or model is not in the active model list."""


class LatencyPoint(ApiModel):
    datetime: str
    available: Availability
    latency_ms: int | None
    error: str | None = None


class LatencyBucket(ApiModel):
    bucket: int
    avg_ms: int | None
    p95_ms: int | None
    count: int


class LatencySummary(ApiModel):
    avg_ms: int | None
    p95_ms: int | None
    count: int


class LatencySeries(ApiModel):
    family: str
    model: str | None
    points: list[LatencyPoint] | None = None
    buckets: list[LatencyBucket] | None = None
    summary: LatencySummary


class LatencyResponse(ApiModel):
    span: Span
    series: list[LatencySeries]


def _stats(latencies: list[int]) -> tuple[int | None, int | None]:
    """Mean and nearest-rank p95, both rounded to whole milliseconds."""
    if not latencies:
        return None, None
    ordered = sorted(latencies)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return round(sum(ordered) / len(ordered)), p95


def _summary(latencies: list[int]) -> LatencySummary:
    avg, p95 = _stats(latencies)
    return LatencySummary(avg_ms=avg, p95_ms=p95, count=len(latencies))


def _bucket_of(round_at: str, span: Span, zone: ZoneInfo) -> int:
    local = datetime.fromisoformat(round_at.replace("Z", "+00:00")).astimezone(zone)
    return {"hour": local.hour, "weekday": local.weekday(), "monthday": local.day}[span]


def _live_points(
    settings: Settings, family: str, names: list[str], model: str | None, now: datetime | None
) -> tuple[list[LatencyPoint], list[int]]:
    """Points on the shared slot grid (see `app.slots`), plus the latencies of the checks behind them."""
    grid = slots.grid(settings.check_interval_seconds, settings.history_limit, now)
    checks = db.checks_since(settings.database_path, family, names, grid[0].start) if grid else []
    points, latencies = [], []
    for slot, bucket in zip(grid, slots.latest_per_slot(grid, checks)):
        ok = [r.latency_ms for r in bucket.values() if r.success and r.latency_ms is not None]
        latencies += ok
        if model is not None:
            check = bucket.get(model)
            points.append(
                LatencyPoint(
                    datetime=slot.end,
                    available=_model_availability(check.success) if check else "unknown",
                    latency_ms=check.latency_ms if check else None,
                    error=check.error if check else None,
                )
            )
        else:
            points.append(
                LatencyPoint(
                    datetime=slot.end,
                    available=_family_availability(sum(r.success for r in bucket.values()), len(bucket)),
                    latency_ms=round(sum(ok) / len(ok)) if ok else None,
                )
            )
    return points, latencies


def _series(
    settings: Settings,
    family: str,
    names: list[str],
    model: str | None,
    span: Span,
    days: int,
    zone: ZoneInfo,
    now: datetime | None,
) -> LatencySeries:
    if span == "live":
        points, latencies = _live_points(settings, family, names, model, now)
        # The summary covers the individual checks of the shown slots, not the per-slot means.
        return LatencySeries(family=family, model=model, points=points, summary=_summary(latencies))

    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    checks = db.latency_checks(settings.database_path, family, names, since)
    grouped: dict[int, list[int]] = {bucket: [] for bucket in BUCKETS[span]}
    for at, latency in checks:
        grouped[_bucket_of(at, span, zone)].append(latency)
    buckets = [
        LatencyBucket(bucket=bucket, avg_ms=avg, p95_ms=p95, count=len(values))
        for bucket, values in grouped.items()
        for avg, p95 in [_stats(values)]
    ]
    return LatencySeries(
        family=family, model=model, buckets=buckets, summary=_summary([latency for _, latency in checks])
    )


def get_latency(
    settings: Settings,
    span: Span,
    days: int,
    zone: ZoneInfo,
    family: str | None = None,
    model: str | None = None,
    now: datetime | None = None,
) -> LatencyResponse:
    """Latency of one model, one family (mean of its successful active models) or every active family.

    Live spans return the last `history_limit` slots of the shared grid; aggregate spans bucket every successful
    check of the last `days` days by local hour of day, weekday (Monday = 0) or day of month in `zone`.
    """
    families = db.active_models(settings.database_path)
    if family is not None:
        families = [f for f in families if f.title == family]
        if not families:
            raise NotFoundError(f"Unknown family: {family}")
    series = []
    for f in families:
        names = [m.modelname for m in f.models]
        if model is not None:
            if model not in names:
                raise NotFoundError(f"Unknown model: {model}")
            names = [model]
        series.append(_series(settings, f.title, names, model, span, days, zone, now))
    return LatencyResponse(span=span, series=series)
