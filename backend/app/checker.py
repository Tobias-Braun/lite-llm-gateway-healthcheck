"""Periodic health checks of all active models (see `app.models`) through the gateway."""

import asyncio
import hashlib
import logging
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

from openai import AsyncOpenAI

from app import db
from app.config import Settings

logger = logging.getLogger(__name__)

# The answer itself is irrelevant; a few tokens keep the checks cheap.
MAX_TOKENS = 16
# Error messages from the gateway can be long HTML/JSON bodies; keep the stored text short.
MAX_ERROR_LENGTH = 500

# Fake data mode: synthetic results and the startup backfill target (see docs/backend.md).
FAKE_LATENCY_RANGE_MS = (50, 400)
FAKE_ERROR_MESSAGE = "Simulated failure (fake data mode)"
FAKE_HISTORY_TARGET = 48
# Share of models deterministically bucketed into the "stable" reliability tier; the rest are
# "flaky" (see docs/backend.md).
STABLE_TIER_PERCENT = 85
STABLE_FAILURE_PROBABILITY = 0.01
FLAKY_OUTAGE_START_PROBABILITY = 0.05
FLAKY_OUTAGE_LENGTH_RANGE = (2, 5)
# Not used for security purposes, just synthetic test data; SystemRandom satisfies SonarCloud's
# pseudorandom-number-generator rating rule (S2245) without changing behaviour.
_fake_random = random.SystemRandom()

# Remaining consecutive failing rounds per flaky model, keyed by `(family title, model name)`;
# 0 or absent means the model is currently healthy. Lives only for the process's lifetime.
FakeOutageState = dict[tuple[str, str], int]


def _format_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return _format_iso(datetime.now(UTC))


def is_flaky_tier(family_title: str, model_name: str) -> bool:
    """Deterministically bucket a model from a hash of its full name (see docs/backend.md)."""
    digest = hashlib.sha256(f"{family_title}/{model_name}".encode()).digest()
    bucket = int.from_bytes(digest, "big") % 100
    return bucket >= STABLE_TIER_PERCENT


def _fake_success() -> tuple[bool, int | None, str | None]:
    return True, _fake_random.randint(*FAKE_LATENCY_RANGE_MS), None


def fake_check_model(
    family_title: str, model_name: str, outage_state: FakeOutageState
) -> tuple[bool, int | None, str | None]:
    """Generate one synthetic result for a model, per its stable/flaky tier (see docs/backend.md).

    `outage_state` tracks each flaky model's remaining failing rounds across calls, so clusters
    of consecutive failures span successive rounds instead of failing independently.
    """
    if not is_flaky_tier(family_title, model_name):
        if _fake_random.random() < STABLE_FAILURE_PROBABILITY:
            return False, None, FAKE_ERROR_MESSAGE
        return _fake_success()

    key = (family_title, model_name)
    remaining = outage_state.get(key, 0)
    if remaining > 0:
        outage_state[key] = remaining - 1
        return False, None, FAKE_ERROR_MESSAGE
    if _fake_random.random() < FLAKY_OUTAGE_START_PROBABILITY:
        outage_state[key] = _fake_random.randint(*FLAKY_OUTAGE_LENGTH_RANGE) - 1
        return False, None, FAKE_ERROR_MESSAGE
    return _fake_success()


def create_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.gateway_url,
        api_key=settings.api_key,
        timeout=settings.request_timeout_seconds,
        max_retries=0,
    )


async def check_model(
    client: AsyncOpenAI, model: str, prompt: str, timeout: float
) -> tuple[bool, int | None, str | None]:
    """Send the prompt to one model and return `(success, latency_ms, error)`.

    Any exception counts as a failed check, so a single broken model never aborts a round.
    """
    start = time.perf_counter()
    try:
        await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - every failure must be recorded, not raised
        message = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
        return False, None, message
    return True, round((time.perf_counter() - start) * 1000), None


async def run_round(
    settings: Settings, client: AsyncOpenAI, fake_outage_state: FakeOutageState | None = None
) -> list[db.CheckResult]:
    """Check all active models concurrently and store the results as one round."""
    round_id = uuid.uuid4().hex
    round_at = utc_now_iso()
    families = await asyncio.to_thread(db.active_models, settings.database_path)
    targets = [(family.title, model.modelname) for family in families for model in family.models]
    if settings.fake_data:
        outage_state = fake_outage_state if fake_outage_state is not None else {}
        outcomes = [fake_check_model(family, model, outage_state) for family, model in targets]
    else:
        tasks = []
        for i, (_, model) in enumerate(targets):
            if i > 0 and settings.request_interval_seconds > 0:
                await asyncio.sleep(settings.request_interval_seconds)
            tasks.append(
                asyncio.create_task(
                    check_model(client, model, settings.healthcheck_prompt, settings.request_timeout_seconds)
                )
            )
        outcomes = await asyncio.gather(*tasks)
    results = [
        db.CheckResult(round_id, round_at, family, model, success, latency_ms, error)
        for (family, model), (success, latency_ms, error) in zip(targets, outcomes, strict=True)
    ]
    await asyncio.to_thread(db.insert_results, settings.database_path, results)
    failed = sum(not r.success for r in results)
    logger.info("Check round %s finished: %d models, %d failed", round_id, len(results), failed)
    return results


async def backfill_fake_history(settings: Settings, fake_outage_state: FakeOutageState | None = None) -> None:
    """Top up every active model with backdated synthetic rounds up to `FAKE_HISTORY_TARGET`.

    A model already at or above the target is left alone. Backfilled rounds of different models
    that land on the same timestamp share one `round_id`, the same as a normal round. Rounds are
    generated oldest to newest per model, through `fake_outage_state`, so a flaky model's clusters
    read consistently and so the state carries over correctly into the live rounds that follow.
    """
    outage_state = fake_outage_state if fake_outage_state is not None else {}
    now = datetime.now(UTC).replace(microsecond=0)
    interval = timedelta(seconds=settings.check_interval_seconds)
    round_ids: dict[str, str] = {}
    results: list[db.CheckResult] = []
    for family in await asyncio.to_thread(db.active_models, settings.database_path):
        for model in family.models:
            count, oldest_at = await asyncio.to_thread(
                db.model_history_bounds, settings.database_path, family.title, model.modelname
            )
            deficit = FAKE_HISTORY_TARGET - count
            if deficit <= 0:
                continue
            anchor = datetime.fromisoformat(oldest_at.replace("Z", "+00:00")) if oldest_at else now
            for i in range(deficit, 0, -1):
                at_iso = _format_iso(anchor - i * interval)
                round_id = round_ids.setdefault(at_iso, uuid.uuid4().hex)
                success, latency_ms, error = fake_check_model(family.title, model.modelname, outage_state)
                results.append(
                    db.CheckResult(round_id, at_iso, family.title, model.modelname, success, latency_ms, error)
                )
    if results:
        await asyncio.to_thread(db.insert_results, settings.database_path, results)


async def run_forever(settings: Settings, client: AsyncOpenAI | None = None) -> None:
    """Run a round immediately and then every `check_interval_seconds` until cancelled."""
    client = client or create_client(settings)
    fake_outage_state: FakeOutageState = {}
    try:
        if settings.fake_data:
            await backfill_fake_history(settings, fake_outage_state)
        while True:
            try:
                await run_round(settings, client, fake_outage_state)
            except Exception:
                logger.exception("Check round failed")
            await asyncio.sleep(settings.check_interval_seconds)
    finally:
        await client.close()
