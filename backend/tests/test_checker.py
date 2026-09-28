import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import checker, db
from app.config import ModelDef, ModelFamily, Settings
from tests.conftest import mock_client


class _ScriptedRandom:
    """A stand-in for `random.SystemRandom` that replays fixed `.random()` values."""

    def __init__(self, values: list[float], randint_value: int = 200) -> None:
        self._values = iter(values)
        self._randint_value = randint_value

    def random(self) -> float:
        return next(self._values)

    def randint(self, _a: int, _b: int) -> int:
        return self._randint_value


def test_failing_model_is_recorded_without_breaking_the_round(settings: Settings) -> None:
    client = mock_client(failing={"claude-opus-5"})

    results = asyncio.run(checker.run_round(settings, client))

    assert len(results) == 4
    assert client.chat.completions.create.await_count == 4
    by_model = {r.model: r for r in results}
    assert by_model["claude-opus-5"].success is False
    assert "claude-opus-5 is down" in by_model["claude-opus-5"].error
    assert by_model["claude-opus-5"].latency_ms is None
    assert by_model["claude-sonnet-5"].success is True
    assert by_model["claude-sonnet-5"].latency_ms is not None
    assert len({r.round_id for r in results}) == 1

    stored = db.latest_results(settings.database_path, "Claude", ["claude-sonnet-5", "claude-opus-5"])
    assert stored["claude-opus-5"].success is False
    assert stored["claude-sonnet-5"].success is True


def test_request_uses_prompt_and_small_token_limit(settings: Settings) -> None:
    client = mock_client()

    asyncio.run(checker.run_round(settings, client))

    kwargs = client.chat.completions.create.await_args_list[0].kwargs
    assert kwargs["messages"] == [{"role": "user", "content": settings.healthcheck_prompt}]
    assert kwargs["max_tokens"] == checker.MAX_TOKENS
    assert kwargs["timeout"] == settings.request_timeout_seconds


def test_request_interval_paces_request_starts(settings: Settings) -> None:
    start_times: list[float] = []

    async def create(*, model: str, **_: object) -> object:
        start_times.append(time.perf_counter())
        return SimpleNamespace(choices=[])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=create))),
        close=AsyncMock(),
    )
    settings.request_interval_seconds = 0.05

    started = time.perf_counter()
    asyncio.run(checker.run_round(settings, client))

    assert len(start_times) == 4
    assert time.perf_counter() - started >= 3 * settings.request_interval_seconds
    gaps = [b - a for a, b in zip(start_times, start_times[1:])]
    assert all(gap >= settings.request_interval_seconds for gap in gaps)


def test_fake_data_round_does_not_call_the_gateway(settings: Settings) -> None:
    settings.fake_data = True
    client = mock_client()

    results = asyncio.run(checker.run_round(settings, client))

    assert len(results) == 4
    client.chat.completions.create.assert_not_awaited()
    assert len({r.round_id for r in results}) == 1
    for r in results:
        if r.success:
            assert 50 <= r.latency_ms <= 400
            assert r.error is None
        else:
            assert r.latency_ms is None
            assert r.error == checker.FAKE_ERROR_MESSAGE


def test_model_tier_is_deterministic_per_name() -> None:
    first = checker.is_flaky_tier("Claude", "claude-opus-5")
    assert checker.is_flaky_tier("Claude", "claude-opus-5") == first
    # A different family/model name may hash into the other tier.
    assert isinstance(checker.is_flaky_tier("GPT", "gpt-5"), bool)


def test_stable_tier_fails_at_the_low_probability(monkeypatch) -> None:
    monkeypatch.setattr(checker, "is_flaky_tier", lambda family, model: False)
    monkeypatch.setattr(checker, "_fake_random", _ScriptedRandom([0.005, 0.5]))
    state: checker.FakeOutageState = {}

    failure = checker.fake_check_model("Claude", "claude-sonnet-5", state)
    success = checker.fake_check_model("Claude", "claude-sonnet-5", state)

    assert failure == (False, None, checker.FAKE_ERROR_MESSAGE)
    assert success[0] is True
    assert 50 <= success[1] <= 400
    assert success[2] is None


def test_flaky_tier_fails_in_consecutive_clusters(monkeypatch) -> None:
    monkeypatch.setattr(checker, "is_flaky_tier", lambda family, model: True)
    # healthy, start a 3-round outage, healthy, healthy.
    monkeypatch.setattr(checker, "_fake_random", _ScriptedRandom([0.5, 0.01, 0.9, 0.9], randint_value=3))
    state: checker.FakeOutageState = {}

    outcomes = [checker.fake_check_model("Claude", "claude-opus-5", state) for _ in range(6)]

    assert [success for success, _, _ in outcomes] == [True, False, False, False, True, True]
    for success, latency_ms, error in outcomes:
        if success:
            assert latency_ms is not None and error is None
        else:
            assert latency_ms is None
            assert error == checker.FAKE_ERROR_MESSAGE


def test_backfill_fake_history_clusters_flaky_failures_chronologically(
    settings: Settings, monkeypatch
) -> None:
    settings.fake_data = True
    settings.check_interval_seconds = 60
    # A single model isolates the scripted random sequence to one outage timeline.
    model = ModelDef(modelname="claude-opus-5", provider="Google", company="Anthropic")
    settings.model_families = [ModelFamily(title="Claude", models=[model])]
    monkeypatch.setattr(checker, "is_flaky_tier", lambda family, model: True)
    # One outage of length 3 near the start of the backfilled history, healthy afterwards.
    randoms = [0.5, 0.01] + [0.9] * 60
    monkeypatch.setattr(checker, "_fake_random", _ScriptedRandom(randoms, randint_value=3))

    asyncio.run(checker.backfill_fake_history(settings))

    rounds = db.model_recent_rounds(settings.database_path, "Claude", "claude-opus-5", limit=48)
    assert len(rounds) == 48
    successes = [success for _, success, _, _ in rounds]
    assert successes[:6] == [True, False, False, False, True, True]
    assert all(successes[6:])


def test_backfill_fake_history_tops_up_to_48_rounds(settings: Settings) -> None:
    settings.fake_data = True
    settings.check_interval_seconds = 60
    # "claude-opus-5" already has one round; every other model starts empty.
    existing = db.CheckResult("r0", checker.utc_now_iso(), "Claude", "claude-opus-5", True, 100, None)
    db.insert_results(settings.database_path, [existing])

    asyncio.run(checker.backfill_fake_history(settings))

    for family in settings.model_families:
        for model in family.models:
            count, _ = db.model_history_bounds(settings.database_path, family.title, model.modelname)
            assert count == 48

    # A model already at the target is left alone on a later restart.
    asyncio.run(checker.backfill_fake_history(settings))
    for family in settings.model_families:
        for model in family.models:
            count, _ = db.model_history_bounds(settings.database_path, family.title, model.modelname)
            assert count == 48


def test_run_forever_survives_a_failing_round(settings: Settings, monkeypatch) -> None:
    calls = 0

    async def flaky_round(*_: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database locked")
        if calls == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(checker, "run_round", flaky_round)
    settings.check_interval_seconds = 0
    client = mock_client()

    try:
        asyncio.run(checker.run_forever(settings, client))
    except asyncio.CancelledError:
        pass

    assert calls == 2
    client.close.assert_awaited_once()
