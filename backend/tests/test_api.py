import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import checker
from app.config import Settings
from app.main import create_app
from tests.conftest import mock_client


def test_health(settings: Settings) -> None:
    with TestClient(create_app(settings, run_checks=False)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_families_response_shape(settings: Settings) -> None:
    # Check all but the last family, which must then show up as never checked.
    checked = settings.model_copy(update={"model_families": settings.model_families[:-1]})
    asyncio.run(checker.run_round(checked, mock_client(failing={"gpt-5"})))

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
    }
    assert claude["models"][0]["modelname"] == "claude-sonnet-5"
    assert claude["models"][0]["lastChecked"] == point["datetime"]

    assert gpt["status"] == "no"
    assert gpt["models"][0]["status"] == "no"
    assert "gpt-5 is down" in gpt["models"][0]["error"]
    assert gpt["models"][0]["latencyMs"] is None

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


def test_background_checker_runs_a_round_on_startup(settings: Settings, monkeypatch) -> None:
    fake = mock_client()
    monkeypatch.setattr(checker, "create_client", lambda _: fake)

    with TestClient(create_app(settings)) as client:
        for _ in range(100):
            if client.get("/api/families").json()[0]["status"] != "unknown":
                break
            time.sleep(0.01)
        families = client.get("/api/families").json()

    assert families[0]["status"] == "yes"
    fake.close.assert_awaited_once()
