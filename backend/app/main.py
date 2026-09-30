"""FastAPI application: API routes, background checker, model list refresh and optional static frontend."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Query
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app import checker, db, models
from app.config import Settings
from app.latency import LatencyResponse, NotFoundError, Span, get_latency
from app.status import FamilyStatus, get_families

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class SPAStaticFiles(StaticFiles):
    """Static files with a fallback to `index.html`, so client-side routes survive a reload."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings, run_checks: bool = True) -> FastAPI:
    """Build the application. `run_checks=False` skips the background checker and model refresh (used in tests)."""

    async def run_background() -> None:
        # The first round must see the freshly fetched list, so the initial refresh comes first.
        await models.refresh_models(settings)
        await asyncio.gather(checker.run_forever(settings), models.run_refresh_forever(settings))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.init_db(settings.database_path)
        task = asyncio.create_task(run_background()) if run_checks else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title=settings.app_title, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def config() -> dict[str, str]:
        return {"title": settings.app_title}

    @app.get("/api/families", response_model=list[FamilyStatus])
    def families() -> list[FamilyStatus]:
        return get_families(settings)

    @app.get("/api/latency", response_model=LatencyResponse)
    def latency(
        span: Span = "live",
        days: Annotated[int, Query(ge=1, le=365)] = 30,
        tz: str = "UTC",
        family: str | None = None,
        model: str | None = None,
    ) -> LatencyResponse:
        if model is not None and family is None:
            raise HTTPException(422, "`model` requires `family`")
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(422, f"Unknown time zone: {tz}") from exc
        try:
            return get_latency(settings, span, days, zone, family, model)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    # Mounted last so the API routes above take precedence over the catch-all static mount.
    if settings.static_dir and settings.static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app(Settings())
