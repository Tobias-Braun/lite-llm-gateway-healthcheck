"""The model list: fetched from LiteLLM's `/model/info`, stored in the database, refreshed daily.

On startup and then once a day (at a random moment in the configured refresh window) the list
is fetched and stored via `db.replace_models`; checks and the dashboard only read the stored
list. A failed fetch keeps the previously stored list. See docs/backend.md.
"""

import asyncio
import logging
import random
import re
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx2

from app import db
from app.config import ModelDef, ModelFamily, Settings

logger = logging.getLogger(__name__)

# Ordered prefix lookup; the first match wins, anything else falls back to `("Other", "Unknown")`.
# Family order here is also the family order on the dashboard.
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
_FAMILY_ORDER = list(dict.fromkeys(family for _pattern, family, _company in _FAMILY_COMPANY_BY_PREFIX))

# LiteLLM provider ids mapped to the label shown on the dashboard; others are title-cased.
_PROVIDER_LABELS = {
    "azure": "Azure",
    "azure_ai": "Azure",
    "vertex_ai": "Google",
    "vertex_ai_beta": "Google",
    "gemini": "Google",
    "bedrock": "AWS",
    "sagemaker": "AWS",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}

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
    """Label of the deployment's provider, from `model_info.litellm_provider` or the LiteLLM params."""
    params = entry.get("litellm_params") or {}
    provider = (
        (entry.get("model_info") or {}).get("litellm_provider")
        or params.get("custom_llm_provider")
        or (params.get("model", "").split("/", 1)[0] if "/" in params.get("model", "") else None)
    )
    if not provider:
        return "Unknown"
    return _PROVIDER_LABELS.get(provider, provider.replace("_", " ").title())


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


def _natural_key(name: str) -> list[tuple[int, int, str]]:
    """Sort key comparing digit runs numerically, so `gpt-10` sorts after `gpt-9`."""
    return [(1, int(part), "") if part.isdigit() else (0, 0, part) for part in re.findall(r"\d+|\D+", name)]


def _group(models: list[tuple[str, ModelDef]]) -> list[ModelFamily]:
    """Group `(family, model)` pairs into families: known families first, newest models first."""
    families: dict[str, list[ModelDef]] = {}
    for family, model in models:
        families.setdefault(family, []).append(model)
    ordered = sorted(families, key=lambda f: (_FAMILY_ORDER.index(f) if f in _FAMILY_ORDER else len(_FAMILY_ORDER), f))
    return [
        ModelFamily(
            title=title,
            models=sorted(families[title], key=lambda m: _natural_key(m.modelname), reverse=True),
        )
        for title in ordered
    ]


def _model_info_url(gateway_url: str) -> str:
    # GATEWAY_URL is the OpenAI-compatible base (ending in /v1); /model/info lives at the root.
    return f"{gateway_url.rstrip('/').removesuffix('/v1')}/model/info"


async def fetch_models(settings: Settings) -> list[ModelFamily]:
    """Fetch the gateway's current chat models, without outdated variants, grouped into families."""
    async with httpx2.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(
            _model_info_url(settings.gateway_url),
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        response.raise_for_status()
    entries = response.json()["data"]

    # Several deployments of one model_name are load-balanced by LiteLLM; the first one wins.
    chat_entries: dict[str, dict[str, Any]] = {}
    for entry in entries:
        # Embedding, image, ... models can't answer a chat completion; a missing mode means chat.
        if (entry.get("model_info") or {}).get("mode") not in ("chat", None):
            continue
        chat_entries.setdefault(entry["model_name"], entry)

    current = drop_outdated(list(chat_entries))
    return _group(
        [
            (
                infer_family(name),
                ModelDef(modelname=name, provider=provider_label(chat_entries[name]), company=infer_company(name)),
            )
            for name in current
        ]
    )


async def refresh_models(settings: Settings) -> bool:
    """Fetch the model list (or the synthetic one in fake data mode) and store it.

    Returns whether the stored list was replaced; on failure the previous list stays in use.
    """
    try:
        families = fake_models() if settings.fake_data else await fetch_models(settings)
        await asyncio.to_thread(db.replace_models, settings.database_path, families)
    except Exception:
        logger.exception("Model list refresh failed; keeping the previously stored list")
        return False
    logger.info("Model list refreshed: %d models", sum(len(family.models) for family in families))
    return True


def next_refresh_delay(now: datetime, settings: Settings, rng: random.Random | None = None) -> float:
    """Seconds from `now` until a random moment in the next refresh window that starts after `now`."""
    tz = ZoneInfo(settings.model_refresh_timezone)
    local_now = now.astimezone(tz)
    start_hour, end_hour = settings.model_refresh_start_hour, settings.model_refresh_end_hour
    span_days = 0 if end_hour > start_hour else 1
    day = local_now.date()
    while True:
        # Local wall-clock times are converted to UTC before any arithmetic, so DST shifts
        # don't distort the window.
        start = datetime.combine(day, time(start_hour), tz).astimezone(UTC)
        if start > now:
            break
        day += timedelta(days=1)
    end_day = day + timedelta(days=span_days)
    end = (
        datetime.combine(end_day + timedelta(days=1), time(0), tz)
        if end_hour == 24
        else datetime.combine(end_day, time(end_hour), tz)
    ).astimezone(UTC)
    offset = (rng or random.SystemRandom()).uniform(0, (end - start).total_seconds())
    return (start - now).total_seconds() + offset


async def run_refresh_forever(settings: Settings) -> None:
    """Refresh the model list once per refresh window until cancelled."""
    while True:
        await asyncio.sleep(next_refresh_delay(datetime.now(UTC), settings))
        await refresh_models(settings)


def fake_models() -> list[ModelFamily]:
    """Built-in synthetic model list for fake data mode; no I/O."""
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
