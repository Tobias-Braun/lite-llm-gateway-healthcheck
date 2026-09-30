from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.main import create_app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert(settings: Settings, at: datetime, family: str, results: dict[str, int | None]) -> None:
    """One round at `at`; a model mapped to `None` failed, otherwise it succeeded with that latency."""
    round_at = _iso(at)
    db.insert_results(
        settings.database_path,
        [
            db.CheckResult(round_at, round_at, family, model, latency is not None, latency, None if latency else "down")
            for model, latency in results.items()
        ],
    )


def _get(settings: Settings, **params: object):
    with TestClient(create_app(settings, run_checks=False)) as client:
        return client.get("/api/latency", params=params)


def test_live_family_mean_excludes_failures(settings: Settings) -> None:
    start = datetime.now(UTC) - timedelta(hours=1)
    _insert(settings, start, "Claude", {"claude-sonnet-5": 100, "claude-opus-5": 300})
    _insert(settings, start + timedelta(minutes=5), "Claude", {"claude-sonnet-5": 200, "claude-opus-5": None})
    _insert(settings, start + timedelta(minutes=10), "Claude", {"claude-sonnet-5": None, "claude-opus-5": None})

    body = _get(settings, family="Claude").json()

    assert body["span"] == "live"
    [series] = body["series"]
    assert series["family"] == "Claude" and series["model"] is None
    assert [(p["available"], p["latencyMs"]) for p in series["points"]] == [
        ("yes", 200),
        ("partial", 200),
        ("no", None),
    ]
    assert series["summary"] == {"avgMs": 200, "p95Ms": 300, "count": 3}


def test_live_model_uses_family_history_limit(settings: Settings) -> None:
    settings.history_limit = 4
    settings.model_history_limit = 2
    start = datetime.now(UTC) - timedelta(hours=1)
    for i in range(5):
        _insert(settings, start + timedelta(minutes=5 * i), "GPT", {"gpt-5": None if i == 4 else 100 + i})

    [series] = _get(settings, family="GPT", model="gpt-5").json()["series"]

    assert [p["latencyMs"] for p in series["points"]] == [101, 102, 103, None]
    assert series["points"][-1]["error"] == "down"
    assert series["model"] == "gpt-5"


def test_aggregate_buckets_in_time_zone(settings: Settings) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
    _insert(settings, yesterday, "GPT", {"gpt-5": 100})
    _insert(settings, yesterday + timedelta(minutes=5), "GPT", {"gpt-5": 300})
    _insert(settings, yesterday + timedelta(minutes=10), "GPT", {"gpt-5": None})
    # Outside the 7-day lookback, so it must not count.
    _insert(settings, yesterday - timedelta(days=10), "GPT", {"gpt-5": 5000})

    [series] = _get(settings, family="GPT", span="hour", days=7, tz="Asia/Tokyo").json()["series"]

    buckets = series["buckets"]
    assert [b["bucket"] for b in buckets] == list(range(24))
    # 23:30 UTC is 08:30 in Tokyo (UTC+9, no DST).
    assert buckets[8] == {"bucket": 8, "avgMs": 200, "p95Ms": 300, "count": 2}
    assert buckets[23] == {"bucket": 23, "avgMs": None, "p95Ms": None, "count": 0}
    assert series["points"] is None
    assert series["summary"]["count"] == 2


def test_aggregate_span_ranges(settings: Settings) -> None:
    for span, expected in {"weekday": list(range(7)), "monthday": list(range(1, 32))}.items():
        [series] = _get(settings, family="GPT", span=span).json()["series"]
        assert [b["bucket"] for b in series["buckets"]] == expected


def test_overview_returns_one_series_per_active_family(settings: Settings) -> None:
    body = _get(settings, span="weekday").json()

    assert [s["family"] for s in body["series"]] == ["Claude", "GPT", "Never checked"]
    assert all(s["summary"] == {"avgMs": None, "p95Ms": None, "count": 0} for s in body["series"])


def test_validation_and_unknown_names(settings: Settings) -> None:
    assert _get(settings, span="year").status_code == 422
    assert _get(settings, days=0).status_code == 422
    assert _get(settings, tz="Mars/Olympus").status_code == 422
    assert _get(settings, model="gpt-5").status_code == 422
    assert _get(settings, family="Nope").status_code == 404
    assert _get(settings, family="GPT", model="claude-opus-5").status_code == 404
