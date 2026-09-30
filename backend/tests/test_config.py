import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_are_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "60")

    settings = Settings(_env_file=None)

    assert settings.check_interval_seconds == 60
    assert settings.healthcheck_prompt == "Reply with OK."


def test_model_refresh_window_defaults_to_5_to_7_berlin_time() -> None:
    settings = Settings(_env_file=None)

    assert (settings.model_refresh_start_hour, settings.model_refresh_end_hour) == (5, 7)
    assert settings.model_refresh_timezone == "Europe/Berlin"


def test_model_refresh_hour_out_of_range_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_REFRESH_START_HOUR", "24")

    with pytest.raises(ValidationError, match="model_refresh_start_hour"):
        Settings(_env_file=None)


def test_fake_data_defaults_to_false() -> None:
    assert Settings(_env_file=None).fake_data is False


def test_fake_data_is_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_DATA", "true")

    assert Settings(_env_file=None).fake_data is True


def test_app_title_defaults_to_gateway_health_check() -> None:
    assert Settings(_env_file=None).app_title == "Gateway Health Check"


def test_app_title_is_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_TITLE", "Acme Gateway")

    assert Settings(_env_file=None).app_title == "Acme Gateway"
