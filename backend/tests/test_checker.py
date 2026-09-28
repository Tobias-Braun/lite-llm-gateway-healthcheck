import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import checker, db
from app.config import Settings
from tests.conftest import mock_client


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
