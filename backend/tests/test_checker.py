import asyncio

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
