import asyncio
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app import db, models
from app.config import ModelDef, ModelFamily, Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, gateway_url="http://gateway.invalid/v1", api_key="secret-key", **overrides)


_RealAsyncClient = httpx2.AsyncClient


def _client_from(handler: Callable[[httpx2.Request], httpx2.Response]) -> Callable[..., httpx2.AsyncClient]:
    def factory(*_args: object, **_kwargs: object) -> httpx2.AsyncClient:
        return _RealAsyncClient(transport=httpx2.MockTransport(handler))

    return factory


def test_fetch_models_keeps_only_chat_mode_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "data": [
                    {
                        "model_name": "claude-sonnet-5",
                        "model_info": {"mode": "chat"},
                        "litellm_params": {"custom_llm_provider": "anthropic"},
                    },
                    {
                        "model_name": "text-embed-3",
                        "model_info": {"mode": "embedding"},
                        "litellm_params": {"custom_llm_provider": "openai"},
                    },
                ]
            },
        )

    monkeypatch.setattr(models.httpx2, "AsyncClient", _client_from(handler))

    families = asyncio.run(models.fetch_models(_settings()))

    assert len(requests) == 1
    assert requests[0].url == "http://gateway.invalid/model/info"
    assert requests[0].headers["authorization"] == "Bearer secret-key"
    assert [model.modelname for family in families for model in family.models] == ["claude-sonnet-5"]


def test_fetch_models_dedupes_by_model_name_keeping_first_occurrence(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "data": [
                    {
                        "model_name": "gpt-5",
                        "model_info": {"mode": "chat"},
                        "litellm_params": {"custom_llm_provider": "azure"},
                    },
                    {
                        "model_name": "gpt-5",
                        "model_info": {"mode": "chat"},
                        "litellm_params": {"custom_llm_provider": "openai"},
                    },
                ]
            },
        )

    monkeypatch.setattr(models.httpx2, "AsyncClient", _client_from(handler))

    families = asyncio.run(models.fetch_models(_settings()))

    assert len(families) == 1
    assert [model.modelname for model in families[0].models] == ["gpt-5"]
    assert families[0].models[0].provider == "Azure"


def test_drop_outdated_keeps_highest_version_per_prefix_and_suffix() -> None:
    names = [
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.1",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "o4-mini",
        "o3-mini",
    ]

    assert models.drop_outdated(names) == [
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-5.6-terra",
        "gpt-5.5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4o",
        "o4-mini",
        "o3-mini",
    ]


@pytest.mark.parametrize(
    ("model_name", "family", "company"),
    [
        ("claude-sonnet-5", "Claude", "Anthropic"),
        ("gemini-2.5-pro", "Gemini", "Google"),
        ("gemma-4-31b-it", "Gemini", "Google"),
        ("gpt-5", "GPT", "OpenAI"),
        ("o3-mini", "GPT", "OpenAI"),
        ("llama-3-3-70b", "Open-weight / Sovereign", "Meta"),
        ("qwen3-235b", "Open-weight / Sovereign", "Alibaba"),
        ("deepseek-v4-flash-sovereign", "Open-weight / Sovereign", "DeepSeek"),
        ("devstral-2-123b", "Open-weight / Sovereign", "Mistral AI"),
        ("mistral-large", "Open-weight / Sovereign", "Mistral AI"),
        ("nemotron-3-super-120b", "Open-weight / Sovereign", "NVIDIA"),
        ("nova-2-lite", "Open-weight / Sovereign", "Amazon"),
        ("some-unknown-model", "Other", "Unknown"),
    ],
)
def test_infer_family_and_company_match_the_prefix_table(model_name: str, family: str, company: str) -> None:
    assert models.infer_family(model_name) == family
    assert models.infer_company(model_name) == company


def test_provider_label_maps_known_litellm_providers() -> None:
    assert models.provider_label({"model_info": {"litellm_provider": "vertex_ai"}}) == "Google"
    assert models.provider_label({"litellm_params": {"custom_llm_provider": "azure"}}) == "Azure"
    assert models.provider_label({"litellm_params": {"model": "bedrock/nova-2-lite"}}) == "AWS"


def test_provider_label_title_cases_unknown_providers() -> None:
    assert models.provider_label({"model_info": {"litellm_provider": "hosted_vllm"}}) == "Hosted Vllm"


def test_provider_label_defaults_to_unknown_when_missing() -> None:
    assert models.provider_label({}) == "Unknown"
    assert models.provider_label({"litellm_params": {}}) == "Unknown"


def test_fake_models_has_the_synthetic_families() -> None:
    families = models.fake_models()

    assert [family.title for family in families] == ["Claude", "Gemini", "GPT", "Open-weight / Sovereign"]
    assert [len(family.models) for family in families] == [11, 7, 17, 12]
    claude = families[0]
    assert claude.models[0].modelname == "claude-fable-5-1"
    assert all(model.provider == "Google" and model.company == "Anthropic" for model in claude.models)
    sovereign = families[3]
    assert {model.modelname for model in sovereign.models} == {
        "qwen-3.6-35b-sovereign",
        "deepseek-v4-flash-sovereign",
        "google/gemma-4-31b-it",
        "llama-3-3-70b",
        "qwen3.8-27b",
        "gpt-oss-120b",
        "gpt-oss-20b",
        "qwen3-coder-480b",
        "qwen3-235b",
        "devstral-2-123b",
        "nemotron-3-super-120b",
        "nova-2-lite",
    }


def _serve(monkeypatch: pytest.MonkeyPatch, entries: list[dict[str, object]]) -> None:
    monkeypatch.setattr(
        models.httpx2, "AsyncClient", _client_from(lambda _request: httpx2.Response(200, json={"data": entries}))
    )


def _entry(name: str, **model_info: object) -> dict[str, object]:
    return {"model_name": name, "model_info": model_info, "litellm_params": {"model": f"azure/{name}"}}


def _names(families: list[ModelFamily]) -> dict[str, list[str]]:
    return {family.title: [model.modelname for model in family.models] for family in families}


def test_fetch_models_keeps_entries_without_mode_drops_outdated_and_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        [
            _entry("gpt-5.4-luna", mode="chat"),
            _entry("gpt-5.5-luna", mode="chat"),
            _entry("some-in-house-model"),
            _entry("gpt-4o"),
            _entry("claude-sonnet-5", mode="chat"),
            _entry("dall-e-4", mode="image_generation"),
        ],
    )

    families = asyncio.run(models.fetch_models(_settings()))

    # Known families come first in prefix-table order, "Other" last; newest models first.
    assert _names(families) == {
        "Claude": ["claude-sonnet-5"],
        "GPT": ["gpt-5.5-luna", "gpt-4o"],
        "Other": ["some-in-house-model"],
    }
    assert list(_names(families)) == ["Claude", "GPT", "Other"]
    assert families[1].models[0] == ModelDef(modelname="gpt-5.5-luna", provider="Azure", company="OpenAI")


def test_refresh_stores_the_list_and_deactivates_disappeared_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(database_path=tmp_path / "db.sqlite")
    db.init_db(settings.database_path)
    _serve(monkeypatch, [_entry("gpt-5.4-luna"), _entry("claude-sonnet-5")])
    assert asyncio.run(models.refresh_models(settings)) is True
    db.insert_results(
        settings.database_path, [db.CheckResult("r1", "2026-09-30T05:00:00Z", "GPT", "gpt-5.4-luna", True, 100, None)]
    )

    # gpt-5.4-luna is outdated by gpt-5.5-luna, claude-sonnet-5 disappeared.
    _serve(monkeypatch, [_entry("gpt-5.4-luna"), _entry("gpt-5.5-luna")])
    assert asyncio.run(models.refresh_models(settings)) is True

    assert _names(db.active_models(settings.database_path)) == {"GPT": ["gpt-5.5-luna"]}
    # Inactive models keep their check history.
    assert db.model_history_bounds(settings.database_path, "GPT", "gpt-5.4-luna")[0] == 1

    # A model that comes back is active again.
    _serve(monkeypatch, [_entry("claude-sonnet-5"), _entry("gpt-5.5-luna")])
    asyncio.run(models.refresh_models(settings))
    assert _names(db.active_models(settings.database_path)) == {
        "Claude": ["claude-sonnet-5"],
        "GPT": ["gpt-5.5-luna"],
    }


def test_failed_refresh_keeps_the_previous_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(database_path=tmp_path / "db.sqlite")
    db.init_db(settings.database_path)
    _serve(monkeypatch, [_entry("claude-sonnet-5")])
    asyncio.run(models.refresh_models(settings))

    monkeypatch.setattr(
        models.httpx2, "AsyncClient", _client_from(lambda _request: httpx2.Response(500, json={"error": "down"}))
    )

    assert asyncio.run(models.refresh_models(settings)) is False
    assert _names(db.active_models(settings.database_path)) == {"Claude": ["claude-sonnet-5"]}


def test_fake_data_refresh_stores_the_synthetic_list_without_calling_the_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(database_path=tmp_path / "db.sqlite", fake_data=True)
    db.init_db(settings.database_path)
    monkeypatch.setattr(models.httpx2, "AsyncClient", None)  # any gateway call would fail

    assert asyncio.run(models.refresh_models(settings)) is True
    assert db.active_models(settings.database_path) == models.fake_models()


class _FixedUniform(random.Random):
    """Picks the given fraction of every `uniform` range."""

    def __init__(self, fraction: float) -> None:
        super().__init__()
        self._fraction = fraction

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._fraction


def _next_refresh(now: datetime, fraction: float, **overrides: object) -> datetime:
    delay = models.next_refresh_delay(now, _settings(**overrides), _FixedUniform(fraction))
    return now + timedelta(seconds=delay)


def test_next_refresh_is_inside_todays_window_before_it_starts() -> None:
    # 01:00 UTC is 03:00 in Berlin (CEST): today's 05:00-07:00 window is still ahead.
    now = datetime(2026, 9, 30, 1, 0, tzinfo=UTC)

    assert _next_refresh(now, 0.0) == datetime(2026, 9, 30, 3, 0, tzinfo=UTC)
    assert _next_refresh(now, 0.5) == datetime(2026, 9, 30, 4, 0, tzinfo=UTC)
    assert _next_refresh(now, 1.0) == datetime(2026, 9, 30, 5, 0, tzinfo=UTC)


def test_next_refresh_moves_to_tomorrow_once_the_window_started() -> None:
    # 03:30 UTC is 05:30 in Berlin: startup already refreshed, the next refresh is tomorrow.
    now = datetime(2026, 9, 30, 3, 30, tzinfo=UTC)

    assert _next_refresh(now, 0.0) == datetime(2026, 10, 1, 3, 0, tzinfo=UTC)


def test_next_refresh_follows_the_configured_timezone_across_dst() -> None:
    # Berlin switches back to CET on 2026-10-25, so 05:00 local is 04:00 UTC afterwards.
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    assert _next_refresh(now, 0.0) == datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
    assert _next_refresh(now, 0.0, model_refresh_timezone="UTC") == datetime(2026, 10, 25, 5, 0, tzinfo=UTC)


def test_next_refresh_window_may_span_midnight() -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    window = {"model_refresh_timezone": "UTC", "model_refresh_start_hour": 23, "model_refresh_end_hour": 1}

    assert _next_refresh(now, 0.0, **window) == datetime(2026, 9, 30, 23, 0, tzinfo=UTC)
    assert _next_refresh(now, 1.0, **window) == datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
