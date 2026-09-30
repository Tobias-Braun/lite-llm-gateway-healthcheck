import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import checker, db, models
from app.config import ModelFamily, Settings
from app.main import create_app
from tests.conftest import FAMILIES, mock_client


def test_health(settings: Settings) -> None:
    with TestClient(create_app(settings, run_checks=False)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_config_returns_app_title(settings: Settings) -> None:
    settings.app_title = "Acme Gateway"

    with TestClient(create_app(settings, run_checks=False)) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"title": "Acme Gateway"}
    assert client.app.title == "Acme Gateway"


def test_families_response_shape(settings: Settings) -> None:
    # Check all but the last family, which must then show up as never checked.
    families = [ModelFamily.model_validate(family) for family in FAMILIES]
    db.replace_models(settings.database_path, families[:-1])
    asyncio.run(checker.run_round(settings, mock_client(failing={"gpt-5"})))
    db.replace_models(settings.database_path, families)

    with TestClient(create_app(settings, run_checks=False)) as client:
        response = client.get("/api/families")

    assert response.status_code == 200
    claude, gpt, never = response.json()
    assert set(claude) == {"title", "status", "history", "models"}
    assert claude["title"] == "Claude"
    assert claude["status"] == "yes"
    [point] = claude["history"]["availabilityPoints"]
    assert set(point) == {"datetime", "available"}
    assert point["available"] == "yes"
    assert point["datetime"].endswith("Z")
    assert set(claude["models"][0]) == {
        "modelname",
        "provider",
        "company",
        "status",
        "lastChecked",
        "latencyMs",
        "error",
        "history",
    }
    assert claude["models"][0]["modelname"] == "claude-sonnet-5"
    assert claude["models"][0]["lastChecked"] == point["datetime"]
    [model_point] = claude["models"][0]["history"]["availabilityPoints"]
    assert model_point["available"] == "yes"
    assert set(model_point) == {"datetime", "available", "latencyMs", "error"}
    assert model_point["latencyMs"] is not None
    assert model_point["error"] is None

    assert gpt["status"] == "no"
    assert gpt["models"][0]["status"] == "no"
    assert "gpt-5 is down" in gpt["models"][0]["error"]
    assert gpt["models"][0]["latencyMs"] is None
    [gpt_point] = gpt["models"][0]["history"]["availabilityPoints"]
    assert gpt_point["available"] == "no"
    assert "gpt-5 is down" in gpt_point["error"]
    assert gpt_point["latencyMs"] is None

    assert never == {
        "title": "Never checked",
        "status": "unknown",
        "history": {"availabilityPoints": []},
        "models": [
            {
                "modelname": "nova-2-lite",
                "provider": "AWS",
                "company": "Amazon",
                "status": "unknown",
                "lastChecked": None,
                "latencyMs": None,
                "error": None,
                "history": {"availabilityPoints": []},
            }
        ],
    }


def test_database_is_created_on_startup(settings: Settings, tmp_path: Path) -> None:
    settings.database_path = tmp_path / "fresh" / "nested" / "db.sqlite"

    with TestClient(create_app(settings, run_checks=False)) as client:
        assert client.get("/api/families").status_code == 200

    assert settings.database_path.exists()


def test_static_dir_is_served_with_spa_fallback(settings: Settings, tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>dashboard</html>")
    (static / "assets" / "app.js").write_text("console.log('hi')")
    settings.static_dir = static

    with TestClient(create_app(settings, run_checks=False)) as client:
        assert client.get("/").text == "<html>dashboard</html>"
        assert client.get("/assets/app.js").text == "console.log('hi')"
        assert client.get("/some/client/route").text == "<html>dashboard</html>"
        assert client.get("/api/health").json() == {"status": "ok"}


def test_background_checker_fetches_models_before_the_first_round(settings: Settings, monkeypatch) -> None:
    fake = mock_client()
    monkeypatch.setattr(checker, "create_client", lambda _: fake)
    fetched = [ModelFamily.model_validate(FAMILIES[1])]

    async def fetch(_settings: Settings) -> list[ModelFamily]:
        return fetched

    monkeypatch.setattr(models, "fetch_models", fetch)

    with TestClient(create_app(settings)) as client:
        for _ in range(100):
            if client.get("/api/families").json()[0]["status"] != "unknown":
                break
            time.sleep(0.01)
        families = client.get("/api/families").json()

    # Only the fetched list is checked and shown; the seeded families became inactive.
    assert [family["title"] for family in families] == ["GPT"]
    assert families[0]["status"] == "yes"
    assert [call.kwargs["model"] for call in fake.chat.completions.create.await_args_list] == ["gpt-5"]
    fake.close.assert_awaited_once()
