"""Shared fixtures.

`app.main` builds a module-level app from the environment on import, so a harmless
configuration is put into the environment before any test module imports it. No test ever
talks to a real gateway: the OpenAI client is always replaced by a mock.
"""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("GATEWAY_URL", "http://gateway.invalid/v1")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("MODEL_FAMILIES", "[]")
os.environ.setdefault("DATABASE_PATH", str(Path(tempfile.mkdtemp()) / "import.db"))

from app import db  # noqa: E402
from app.config import Settings  # noqa: E402

FAMILIES = [
    {
        "title": "Claude",
        "models": [
            {"modelname": "claude-sonnet-5", "provider": "Google", "company": "Anthropic"},
            {"modelname": "claude-opus-5", "provider": "Google", "company": "Anthropic"},
        ],
    },
    {
        "title": "GPT",
        "models": [{"modelname": "gpt-5", "provider": "Azure", "company": "OpenAI"}],
    },
    {
        "title": "Never checked",
        "models": [{"modelname": "nova-2-lite", "provider": "AWS", "company": "Amazon"}],
    },
]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        _env_file=None,
        gateway_url="http://gateway.invalid/v1",
        api_key="test-key",
        model_families=FAMILIES,
        database_path=tmp_path / "data" / "healthcheck.db",
        history_limit=3,
    )
    db.init_db(s.database_path)
    return s


def mock_client(failing: set[str] = frozenset()) -> SimpleNamespace:
    """A stand-in for `AsyncOpenAI` whose completions fail for the given model names."""

    async def create(*, model: str, **_: object) -> object:
        if model in failing:
            raise RuntimeError(f"{model} is down")
        return SimpleNamespace(choices=[])

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=create))),
        close=AsyncMock(),
    )
