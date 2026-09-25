from app import db
from app.config import Settings
from app.status import get_families


def _round(settings: Settings, round_id: str, round_at: str, outcomes: dict[tuple[str, str], bool]) -> None:
    db.insert_results(
        settings.database_path,
        [
            db.CheckResult(round_id, round_at, family, model, ok, 100 if ok else None, None if ok else "boom")
            for (family, model), ok in outcomes.items()
        ],
    )


def test_rounds_are_aggregated_per_family(settings: Settings) -> None:
    all_ok = {("Claude", "claude-sonnet-5"): True, ("Claude", "claude-opus-5"): True, ("GPT", "gpt-5"): True}
    one_down = {**all_ok, ("Claude", "claude-opus-5"): False}
    _round(settings, "r1", "2026-09-25T15:00:00Z", all_ok)
    _round(settings, "r2", "2026-09-25T15:05:00Z", one_down)
    _round(settings, "r3", "2026-09-25T15:10:00Z", all_ok)
    _round(settings, "r4", "2026-09-25T15:15:00Z", one_down)

    claude, gpt, never = get_families(settings)

    # history_limit is 3 in the fixture: the oldest round is dropped, order is oldest first.
    assert [(p.datetime, p.available) for p in claude.history.availability_points] == [
        ("2026-09-25T15:05:00Z", "no"),
        ("2026-09-25T15:10:00Z", "yes"),
        ("2026-09-25T15:15:00Z", "no"),
    ]
    assert claude.status == "no"
    assert [m.status for m in claude.models] == ["yes", "no"]
    assert claude.models[1].error == "boom"
    assert claude.models[1].last_checked == "2026-09-25T15:15:00Z"

    assert [p.available for p in gpt.history.availability_points] == ["yes", "yes", "yes"]
    assert gpt.status == "yes"
    assert gpt.models[0].latency_ms == 100

    assert never.status == "unknown"
    assert never.history.availability_points == []
    assert never.models[0].status == "unknown"
    assert never.models[0].last_checked is None


def test_removed_models_are_ignored(settings: Settings) -> None:
    _round(
        settings,
        "r1",
        "2026-09-25T15:00:00Z",
        {("GPT", "gpt-5"): True, ("GPT", "gpt-4o-removed"): False},
    )

    gpt = get_families(settings)[1]

    assert gpt.status == "yes"
    assert [m.modelname for m in gpt.models] == ["gpt-5"]
