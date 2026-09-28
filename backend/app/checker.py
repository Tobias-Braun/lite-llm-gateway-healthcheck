"""Periodic health checks of all configured models through the gateway."""

import asyncio
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

# Fake data mode: synthetic results and the startup backfill target (see spec/backend.md).
FAKE_SUCCESS_PROBABILITY = 0.9
FAKE_LATENCY_RANGE_MS = (50, 400)
FAKE_ERROR_MESSAGE = "Simulated failure (fake data mode)"
FAKE_HISTORY_TARGET = 48


def _format_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return _format_iso(datetime.now(UTC))


def fake_check_model() -> tuple[bool, int | None, str | None]:
    """Generate a synthetic result: 90% success with a fake latency, else a placeholder error."""
    if random.random() < FAKE_SUCCESS_PROBABILITY:
        return True, random.randint(*FAKE_LATENCY_RANGE_MS), None
    return False, None, FAKE_ERROR_MESSAGE


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


async def run_round(settings: Settings, client: AsyncOpenAI) -> list[db.CheckResult]:
    """Check all models of all families concurrently and store the results as one round."""
    round_id = uuid.uuid4().hex
    round_at = utc_now_iso()
    targets = [(family.title, model.modelname) for family in settings.model_families for model in family.models]
    if settings.fake_data:
        outcomes = [fake_check_model() for _ in targets]
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


async def backfill_fake_history(settings: Settings) -> None:
    """Top up every configured model with backdated synthetic rounds up to `FAKE_HISTORY_TARGET`.

    A model already at or above the target is left alone. Backfilled rounds of different models
    that land on the same timestamp share one `round_id`, the same as a normal round.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    interval = timedelta(seconds=settings.check_interval_seconds)
    round_ids: dict[str, str] = {}
    results: list[db.CheckResult] = []
    for family in settings.model_families:
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
                success, latency_ms, error = fake_check_model()
                results.append(
                    db.CheckResult(round_id, at_iso, family.title, model.modelname, success, latency_ms, error)
                )
    if results:
        await asyncio.to_thread(db.insert_results, settings.database_path, results)


async def run_forever(settings: Settings, client: AsyncOpenAI | None = None) -> None:
    """Run a round immediately and then every `check_interval_seconds` until cancelled."""
    client = client or create_client(settings)
    try:
        if settings.fake_data:
            await backfill_fake_history(settings)
        while True:
            try:
                await run_round(settings, client)
            except Exception:
                logger.exception("Check round failed")
            await asyncio.sleep(settings.check_interval_seconds)
    finally:
        await client.close()
