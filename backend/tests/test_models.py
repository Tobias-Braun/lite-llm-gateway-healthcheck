import asyncio
from collections.abc import Callable

import httpx2
import pytest

from app import models
from app.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, gateway_url="http://gateway.invalid", api_key="secret-key", model_families=[])


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


def test_provider_label_title_cases_the_underscored_provider() -> None:
    entry = {"litellm_params": {"custom_llm_provider": "vertex_ai"}}
    assert models.provider_label(entry) == "Vertex Ai"


def test_provider_label_defaults_to_unknown_when_missing() -> None:
    assert models.provider_label({}) == "Unknown"
    assert models.provider_label({"litellm_params": {}}) == "Unknown"


def test_fake_models_matches_the_env_example_shape() -> None:
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
