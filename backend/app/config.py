"""Application settings, read from the environment and an optional `.env` file."""

from pathlib import Path

from pydantic import BaseModel, Field
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

    The models to check are not configured here: they are fetched from the gateway and stored
    in the database (see `app.models`).
    """

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT_ENV, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gateway_url: str
    api_key: str
    check_interval_seconds: float = 300
    healthcheck_prompt: str = "Reply with OK."
    request_timeout_seconds: float = 30
    request_interval_seconds: float = 2
    # Daily model list refresh at a random moment in [start, end) local time; an end at or
    # before the start spans midnight.
    model_refresh_start_hour: int = Field(5, ge=0, le=23)
    model_refresh_end_hour: int = Field(7, ge=0, le=24)
    model_refresh_timezone: str = "Europe/Berlin"
    fake_data: bool = False
    app_title: str = "Gateway Health Check"
    database_path: Path = Path("data/healthcheck.db")
    history_limit: int = 50
    model_history_limit: int = 24
    static_dir: Path | None = None
