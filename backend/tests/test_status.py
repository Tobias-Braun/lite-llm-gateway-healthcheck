from datetime import UTC, datetime

from app import db
from app.config import Settings
from app.status import get_families

# Request time for every test: with the default 300 s interval and history_limit 3, the slot
# grid ends 15:20:00 and its slots are (15:05, 15:10], (15:10, 15:15], (15:15, 15:20].
NOW = datetime(2026, 9, 25, 15, 20, tzinfo=UTC)
SLOT_ENDS = ["2026-09-25T15:10:00Z", "2026-09-25T15:15:00Z", "2026-09-25T15:20:00Z"]


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
    _round(settings, "r1", "2026-09-25T15:04:00Z", all_ok)
    _round(settings, "r2", "2026-09-25T15:09:00Z", one_down)
    _round(settings, "r3", "2026-09-25T15:14:00Z", all_ok)
    _round(settings, "r4", "2026-09-25T15:19:00Z", one_down)

    claude, gpt, never = get_families(settings, NOW)

    # r1 is before the grid. Points are labelled with their slot end, oldest first.
    # One model down out of two is a mixed round: `partial`, not `no`.
    assert [(p.datetime, p.available) for p in claude.history.availability_points] == [
        (SLOT_ENDS[0], "partial"),
        (SLOT_ENDS[1], "yes"),
        (SLOT_ENDS[2], "partial"),
    ]
    assert claude.status == "partial"
    assert [m.status for m in claude.models] == ["yes", "no"]
    assert claude.models[1].error == "boom"
    assert claude.models[1].last_checked == "2026-09-25T15:19:00Z"
    # Each model's own history only ever holds `yes`/`no`/`unknown`, independent of the family's mix.
    assert [p.available for p in claude.models[0].history.availability_points] == ["yes", "yes", "yes"]
    assert [p.available for p in claude.models[1].history.availability_points] == ["no", "yes", "no"]
    # Model-level points additionally carry that round's latency/error; family points don't.
    assert [p.latency_ms for p in claude.models[0].history.availability_points] == [100, 100, 100]
    assert [p.error for p in claude.models[1].history.availability_points] == ["boom", None, "boom"]
    assert not hasattr(claude.history.availability_points[0], "latency_ms")

    assert [p.available for p in gpt.history.availability_points] == ["yes", "yes", "yes"]
    assert gpt.status == "yes"
    assert gpt.models[0].latency_ms == 100

    # Never-checked families and models still get the full grid, all `unknown`.
    assert never.status == "unknown"
    assert [(p.datetime, p.available) for p in never.history.availability_points] == [
        (end, "unknown") for end in SLOT_ENDS
    ]
    assert never.models[0].status == "unknown"
    assert never.models[0].last_checked is None
    assert [p.available for p in never.models[0].history.availability_points] == ["unknown"] * 3


def test_family_is_no_only_when_every_model_fails(settings: Settings) -> None:
    all_down = {("Claude", "claude-sonnet-5"): False, ("Claude", "claude-opus-5"): False}
    _round(settings, "r1", "2026-09-25T15:19:00Z", all_down)

    claude = get_families(settings, NOW)[0]

    assert claude.status == "no"
    assert [p.available for p in claude.history.availability_points] == ["unknown", "unknown", "no"]


def test_slots_are_shared_across_families_and_filled_with_unknown(settings: Settings) -> None:
    # GPT misses the middle slot; Claude is only checked in the oldest slot, twice (latest wins).
    _round(settings, "r1", "2026-09-25T15:06:00Z", {("Claude", "claude-sonnet-5"): False, ("GPT", "gpt-5"): True})
    _round(settings, "r2", "2026-09-25T15:08:00Z", {("Claude", "claude-sonnet-5"): True})
    _round(settings, "r3", "2026-09-25T15:18:00Z", {("GPT", "gpt-5"): False})

    claude, gpt, _ = get_families(settings, NOW)

    assert [p.datetime for p in claude.history.availability_points] == SLOT_ENDS
    assert [p.datetime for p in gpt.history.availability_points] == SLOT_ENDS
    assert [p.available for p in claude.history.availability_points] == ["yes", "unknown", "unknown"]
    assert [p.available for p in claude.models[0].history.availability_points] == ["yes", "unknown", "unknown"]
    assert [p.available for p in claude.models[1].history.availability_points] == ["unknown"] * 3
    assert [p.available for p in gpt.history.availability_points] == ["yes", "unknown", "no"]


def test_model_history_window_is_independent_of_family_history_limit(settings: Settings) -> None:
    # model_history_limit (2) is narrower than history_limit (3): the model's window is the most
    # recent part of the same grid.
    narrow = settings.model_copy(update={"model_history_limit": 2})
    all_ok = {("Claude", "claude-sonnet-5"): True, ("Claude", "claude-opus-5"): True, ("GPT", "gpt-5"): True}
    one_down = {**all_ok, ("Claude", "claude-opus-5"): False}
    _round(narrow, "r1", "2026-09-25T15:09:00Z", all_ok)
    _round(narrow, "r2", "2026-09-25T15:14:00Z", one_down)
    _round(narrow, "r3", "2026-09-25T15:19:00Z", all_ok)

    claude = get_families(narrow, NOW)[0]

    assert [p.datetime for p in claude.history.availability_points] == SLOT_ENDS
    assert [p.datetime for p in claude.models[1].history.availability_points] == SLOT_ENDS[1:]
    assert [p.available for p in claude.models[1].history.availability_points] == ["no", "yes"]


def test_removed_models_are_ignored(settings: Settings) -> None:
    _round(
        settings,
        "r1",
        "2026-09-25T15:19:00Z",
        {("GPT", "gpt-5"): True, ("GPT", "gpt-4o-removed"): False},
    )

    gpt = get_families(settings, NOW)[1]

    assert gpt.status == "yes"
    assert [m.modelname for m in gpt.models] == ["gpt-5"]
