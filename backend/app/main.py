"""FastAPI application: API routes, background checker and optional static frontend."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app import checker, db
from app.config import Settings
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
    """Build the application. `run_checks=False` skips the background checker (used in tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.init_db(settings.database_path)
        task = asyncio.create_task(checker.run_forever(settings)) if run_checks else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="LiteLLM Gateway Health Check", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/families", response_model=list[FamilyStatus])
    def families() -> list[FamilyStatus]:
        return get_families(settings)

    # Mounted last so the API routes above take precedence over the catch-all static mount.
    if settings.static_dir and settings.static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app(Settings())
