import pytest
from pydantic_settings import SettingsError

from app.config import Settings


def test_model_families_are_parsed_from_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODEL_FAMILIES",
        '[{"title": "Claude", "models": [{"modelname": "claude-sonnet-5", "provider": "Google", "company": "Anthropic"}]}]',
    )
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "60")

    settings = Settings(_env_file=None)

    assert settings.model_families[0].title == "Claude"
    assert settings.model_families[0].models[0].modelname == "claude-sonnet-5"
    assert settings.check_interval_seconds == 60
    assert settings.healthcheck_prompt == "Reply with OK."


def test_invalid_model_families_json_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FAMILIES", "[{not json")

    with pytest.raises(SettingsError, match="model_families"):
        Settings(_env_file=None)


def test_fake_data_defaults_to_false(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FAMILIES", "[]")

    assert Settings(_env_file=None).fake_data is False


def test_fake_data_is_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FAMILIES", "[]")
    monkeypatch.setenv("FAKE_DATA", "true")

    assert Settings(_env_file=None).fake_data is True


def test_app_title_defaults_to_gateway_health_check(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FAMILIES", "[]")

    assert Settings(_env_file=None).app_title == "Gateway Health Check"


def test_app_title_is_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_FAMILIES", "[]")
    monkeypatch.setenv("APP_TITLE", "Acme Gateway")

    assert Settings(_env_file=None).app_title == "Acme Gateway"
