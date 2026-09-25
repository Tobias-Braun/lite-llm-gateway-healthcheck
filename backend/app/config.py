"""Application settings, read from the environment and an optional `.env` file."""

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# The `.env` file normally lives in the repository root, while the server is started from
# inside `backend/`. Both locations are checked; later entries take precedence.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class ModelDef(BaseModel):
    modelname: str
    provider: str
    company: str


class ModelFamily(BaseModel):
    title: str
    models: list[ModelDef]


class Settings(BaseSettings):
    """Configuration of the health check.

    `MODEL_FAMILIES` is parsed from JSON by pydantic-settings; malformed JSON or a wrong
    shape raises an error at startup, so the server never runs with a broken configuration.
    """

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT_ENV, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gateway_url: str
    api_key: str
    model_families: list[ModelFamily]
    check_interval_seconds: float = 300
    healthcheck_prompt: str = "Reply with OK."
    request_timeout_seconds: float = 30
    database_path: Path = Path("data/healthcheck.db")
    history_limit: int = 50
    static_dir: Path | None = None
