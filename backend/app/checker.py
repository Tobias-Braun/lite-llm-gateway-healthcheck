"""Periodic health checks of all configured models through the gateway."""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from openai import AsyncOpenAI

from app import db
from app.config import Settings

logger = logging.getLogger(__name__)

# The answer itself is irrelevant; a few tokens keep the checks cheap.
MAX_TOKENS = 16
# Error messages from the gateway can be long HTML/JSON bodies; keep the stored text short.
MAX_ERROR_LENGTH = 500


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    outcomes = await asyncio.gather(
        *(
            check_model(client, model, settings.healthcheck_prompt, settings.request_timeout_seconds)
            for _, model in targets
        )
    )
    results = [
        db.CheckResult(round_id, round_at, family, model, success, latency_ms, error)
        for (family, model), (success, latency_ms, error) in zip(targets, outcomes, strict=True)
    ]
    await asyncio.to_thread(db.insert_results, settings.database_path, results)
    failed = sum(not r.success for r in results)
    logger.info("Check round %s finished: %d models, %d failed", round_id, len(results), failed)
    return results


async def run_forever(settings: Settings, client: AsyncOpenAI | None = None) -> None:
    """Run a round immediately and then every `check_interval_seconds` until cancelled."""
    client = client or create_client(settings)
    try:
        while True:
            try:
                await run_round(settings, client)
            except Exception:
                logger.exception("Check round failed")
            await asyncio.sleep(settings.check_interval_seconds)
    finally:
        await client.close()
