# LiteLLM Gateway Health Check

A dockerized FastAPI service that periodically sends a health-check prompt to every chat
model of a LiteLLM gateway, stores the results in SQLite and shows the
availability per model family in a small React dashboard.

The documentation lives in [docs/README.md](docs/README.md). Work is tracked in GitHub issues.

## Quick start (Docker Compose)

```sh
cp .env.example .env          # then set GATEWAY_URL and API_KEY
docker compose up --build
```

Open `http://localhost:8000` for the dashboard. The SQLite database lives in a named volume
mounted at `/data`, so results survive `docker compose down` and rebuilds (`down -v` deletes them). See [.env.example](.env.example) for every
setting; the ones you'll typically change:

| Variable | Purpose |
|---|---|
| `GATEWAY_URL` | OpenAI-compatible base URL of the gateway (including `/v1`) |
| `API_KEY` | Gateway API key |
| `MODEL_REFRESH_TIMEZONE` | Timezone of the daily model list refresh window, 05:00–07:00 by default (default `Europe/Berlin`) |
| `CHECK_INTERVAL_SECONDS` | Seconds between two check rounds (default 300) |
| `REQUEST_INTERVAL_SECONDS` | Minimum spacing between the start of two requests within a round (default 2) |
| `HISTORY_LIMIT` | Rounds of history returned per family (default 50) |
| `FAKE_DATA` | Set to `true` to try the dashboard with synthetic data, no real gateway or API key needed (default `false`) |

## Backend

FastAPI app in `backend/` (Python 3.12+). On startup it creates the SQLite database, fetches the
model list from the gateway's LiteLLM `/model/info` (refreshed daily; outdated variants and
non-chat models are skipped), runs a check round immediately and then every
`CHECK_INTERVAL_SECONDS`, sending `HEALTHCHECK_PROMPT` to every model concurrently. Results are stored per model and aggregated per family.

Run locally:

```sh
cp .env.example .env          # then set GATEWAY_URL and API_KEY
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
```

The `.env` file is read from the repository root or from `backend/`; environment variables take
precedence. All settings are documented in [.env.example](.env.example).

Endpoints:

- `GET /api/families` – status, availability history (one point per round, oldest first) and
  per-model results for every family of the current model list
- `GET /api/latency` – live or aggregated (hour of day, day of week, day of month) latency per
  family, model or across all families (see [docs/api-latency.md](docs/api-latency.md))
- `GET /api/health` – liveness probe, returns `{"status": "ok"}`
- `/` – the built frontend, if `STATIC_DIR` points to an existing directory

Tests (the OpenAI client is mocked, no gateway needed):

```sh
cd backend
.venv/bin/python -m pytest
```

## Frontend

The dashboard in `frontend/` is a Vite + React + TypeScript app without a UI library (charts use
d3). It fetches `/api/families` on load and every 30 seconds and shows one accordion panel per
model family, with the availability timeline directly below each title. A latency overview sits
above the families; open panels and expanded model rows show their own latency charts.

```sh
cd frontend
npm ci
npm run dev    # dev server on http://localhost:5173, proxies /api to http://localhost:8000
npm test       # Vitest + Testing Library
npm run build  # type-check and build into frontend/dist/ (served by the backend at /)
