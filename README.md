# LiteLLM Gateway Health Check

A dockerized FastAPI service that periodically sends a health-check prompt to every configured
model of an OpenAI-compatible (LiteLLM-like) gateway, stores the results in SQLite and shows the
availability per model family in a small React dashboard.

The full requirements live in [prompt.txt](prompt.txt). Work is tracked in GitHub issues.

## Quick start (Docker Compose)

```sh
cp .env.example .env          # then set GATEWAY_URL, API_KEY and MODEL_FAMILIES
docker compose up --build
```

Open `http://localhost:8000` for the dashboard. The SQLite database lives in a named volume
mounted at `/data`, so results survive a restart. See [.env.example](.env.example) for every
setting; the ones you'll typically change:

| Variable | Purpose |
|---|---|
| `GATEWAY_URL` | OpenAI-compatible base URL of the gateway (including `/v1`) |
| `API_KEY` | Gateway API key |
| `MODEL_FAMILIES` | Families and models to check, as single-line JSON |
| `CHECK_INTERVAL_SECONDS` | Seconds between two check rounds (default 300) |
| `HISTORY_LIMIT` | Rounds of history returned per family (default 50) |

## Backend

FastAPI app in `backend/` (Python 3.12+). On startup it creates the SQLite database, runs a
check round immediately and then every `CHECK_INTERVAL_SECONDS`, sending `HEALTHCHECK_PROMPT`
to every configured model concurrently. Results are stored per model and aggregated per family.

Run locally:

```sh
cp .env.example .env          # then set GATEWAY_URL, API_KEY and MODEL_FAMILIES
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
```

The `.env` file is read from the repository root or from `backend/`; environment variables take
precedence. All settings are documented in [.env.example](.env.example).

Endpoints:

- `GET /api/families` – status, availability history (one point per round, oldest first) and
  per-model results for every family, in configuration order
- `GET /api/health` – liveness probe, returns `{"status": "ok"}`
- `/` – the built frontend, if `STATIC_DIR` points to an existing directory

Tests (the OpenAI client is mocked, no gateway needed):

```sh
cd backend
.venv/bin/python -m pytest
```

## Frontend

The dashboard in `frontend/` is a Vite + React + TypeScript app without a UI library. It fetches
`/api/families` on load and every 30 seconds and shows one accordion panel per model family, with
the availability timeline directly below each title.

```sh
cd frontend
npm ci
npm run dev    # dev server on http://localhost:5173, proxies /api to http://localhost:8000
npm test       # Vitest + Testing Library
npm run build  # type-check and build into frontend/dist/ (served by the backend at /)
