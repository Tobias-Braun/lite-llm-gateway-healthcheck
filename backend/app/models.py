"""Derives the model list from LiteLLM's `/model/info` endpoint.

Pure functions, not wired into the running app yet: a later issue will decide how (or whether)
`fetch_models`/`fake_models` replace `Settings.model_families`.
"""

import re
from typing import Any

import httpx2

from app.config import ModelDef, ModelFamily, Settings

# Ordered prefix lookup, seeded from `.env.example`'s `MODEL_FAMILIES`. First match wins;
# anything else falls back to `("Other", "Unknown")`.
_FAMILY_COMPANY_BY_PREFIX: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^claude"), "Claude", "Anthropic"),
    (re.compile(r"^(gemini|gemma)"), "Gemini", "Google"),
    (re.compile(r"^(gpt|o[0-9])"), "GPT", "OpenAI"),
    (re.compile(r"^llama"), "Open-weight / Sovereign", "Meta"),
    (re.compile(r"^qwen"), "Open-weight / Sovereign", "Alibaba"),
    (re.compile(r"^deepseek"), "Open-weight / Sovereign", "DeepSeek"),
    (re.compile(r"^(devstral|mistral)"), "Open-weight / Sovereign", "Mistral AI"),
    (re.compile(r"^nemotron"), "Open-weight / Sovereign", "NVIDIA"),
    (re.compile(r"^nova"), "Open-weight / Sovereign", "Amazon"),
]

# `prefix-version-suffix`, e.g. `gpt-5.6-terra` -> prefix "gpt", version "5.6", suffix "-terra".
# Names that don't match (e.g. `gpt-4o`, `o3-mini`) are unparseable and always kept.
_VERSIONED_NAME_RE = re.compile(
    r"^(?P<prefix>[a-zA-Z][a-zA-Z0-9]*(?:-[a-zA-Z][a-zA-Z0-9]*)*)-"
    r"(?P<version>\d+(?:[.-]\d+)*)"
    r"(?P<suffix>(?:-[a-zA-Z][a-zA-Z0-9]*)*)$"
)


def infer_family(model_name: str) -> str:
    for pattern, family, _company in _FAMILY_COMPANY_BY_PREFIX:
        if pattern.match(model_name):
            return family
    return "Other"


def infer_company(model_name: str) -> str:
    for pattern, _family, company in _FAMILY_COMPANY_BY_PREFIX:
        if pattern.match(model_name):
            return company
    return "Unknown"


def provider_label(entry: dict[str, Any]) -> str:
    provider = entry.get("litellm_params", {}).get("custom_llm_provider")
    if not provider:
        return "Unknown"
    return provider.replace("_", " ").title()


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.split(r"[.-]", version))


def drop_outdated(model_names: list[str]) -> list[str]:
    """Keep only the highest-version name per `(prefix, suffix)` group; unparseable names always survive."""
    groups: dict[int, tuple[str, str]] = {}
    best_index_by_group: dict[tuple[str, str], tuple[int, tuple[int, ...]]] = {}
    for index, name in enumerate(model_names):
        match = _VERSIONED_NAME_RE.match(name)
        if not match:
            continue
        group = (match["prefix"], match["suffix"])
        groups[index] = group
        version = _version_key(match["version"])
        best = best_index_by_group.get(group)
        if best is None or version > best[1]:
            best_index_by_group[group] = (index, version)

    kept_indexes = {index for index, _version in best_index_by_group.values()}
    return [name for index, name in enumerate(model_names) if index not in groups or index in kept_indexes]


async def fetch_models(settings: Settings) -> list[ModelFamily]:
    """Fetch the gateway's chat models and group them into families (see `infer_family`)."""
    async with httpx2.AsyncClient() as client:
        response = await client.get(
            f"{settings.gateway_url}/model/info",
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        response.raise_for_status()
    entries = response.json()["data"]

    seen_names: set[str] = set()
    chat_entries: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("model_info", {}).get("mode") != "chat":
            continue
        name = entry["model_name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        chat_entries.append(entry)

    kept_names = set(drop_outdated([entry["model_name"] for entry in chat_entries]))

    families: dict[str, ModelFamily] = {}
    for entry in chat_entries:
        name = entry["model_name"]
        if name not in kept_names:
            continue
        family_title = infer_family(name)
        model = ModelDef(modelname=name, provider=provider_label(entry), company=infer_company(name))
        families.setdefault(family_title, ModelFamily(title=family_title, models=[])).models.append(model)

    return list(families.values())


def fake_models() -> list[ModelFamily]:
    """The same 4 families as `.env.example`'s `MODEL_FAMILIES`, with no I/O."""
    return [
        ModelFamily(
            title="Claude",
            models=[
                ModelDef(modelname="claude-fable-5-1", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-5-5", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-5", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-sonnet-5", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-4-8", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-4-7", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-4-6", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-sonnet-4-6", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-opus-4-5", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-sonnet-4-5", provider="Google", company="Anthropic"),
                ModelDef(modelname="claude-haiku-4-5", provider="Google", company="Anthropic"),
            ],
        ),
        ModelFamily(
            title="Gemini",
            models=[
                ModelDef(modelname="gemini-3.8-flash", provider="Google", company="Google"),
                ModelDef(modelname="gemini-3.7-flash", provider="Google", company="Google"),
                ModelDef(modelname="gemini-3.6-flash", provider="Google", company="Google"),
                ModelDef(modelname="gemini-3.5-flash", provider="Google", company="Google"),
                ModelDef(modelname="gemini-3.5-flash-lite", provider="Google", company="Google"),
                ModelDef(modelname="gemini-2.5-pro", provider="Google", company="Google"),
                ModelDef(modelname="gemini-2.5-flash", provider="Google", company="Google"),
            ],
        ),
        ModelFamily(
            title="GPT",
            models=[
                ModelDef(modelname="gpt-6-sol", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-6-luna", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.6-sol", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.6-terra", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.6-luna", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.5", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.4", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5.1", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5-mini", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-5-nano", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-4.1", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-4.1-mini", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-4.1-nano", provider="Azure", company="OpenAI"),
                ModelDef(modelname="gpt-4o", provider="Azure", company="OpenAI"),
                ModelDef(modelname="o4-mini", provider="Azure", company="OpenAI"),
                ModelDef(modelname="o3-mini", provider="Azure", company="OpenAI"),
            ],
        ),
        ModelFamily(
            title="Open-weight / Sovereign",
            models=[
                ModelDef(modelname="qwen-3.6-35b-sovereign", provider="adesso", company="Alibaba"),
                ModelDef(modelname="deepseek-v4-flash-sovereign", provider="adesso", company="DeepSeek"),
                ModelDef(modelname="google/gemma-4-31b-it", provider="StackIT", company="Google"),
                ModelDef(modelname="llama-3-3-70b", provider="StackIT", company="Meta"),
                ModelDef(modelname="qwen3.8-27b", provider="StackIT", company="Alibaba"),
                ModelDef(modelname="gpt-oss-120b", provider="AWS", company="OpenAI"),
                ModelDef(modelname="gpt-oss-20b", provider="AWS", company="OpenAI"),
                ModelDef(modelname="qwen3-coder-480b", provider="AWS", company="Alibaba"),
                ModelDef(modelname="qwen3-235b", provider="AWS", company="Alibaba"),
                ModelDef(modelname="devstral-2-123b", provider="AWS", company="Mistral AI"),
                ModelDef(modelname="nemotron-3-super-120b", provider="AWS", company="NVIDIA"),
                ModelDef(modelname="nova-2-lite", provider="AWS", company="Amazon"),
            ],
        ),
    ]
