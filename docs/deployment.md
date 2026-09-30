# Deployment

Ships `backend/` and `frontend/` as one Docker image, run with Docker Compose.

## Image (multi-stage `Dockerfile` in repo root)

**Stage 1 — `node:24-alpine`**: `npm ci && npm run build` in `frontend/`, producing
`frontend/dist`.

**Stage 2 — `python:3.12-slim`**:
- Install `backend/requirements.txt`.
- Copy `backend/app` and stage 1's `frontend/dist` into `/app/static`.
- Environment: `STATIC_DIR=/app/static`, `DATABASE_PATH=/data/healthcheck.db`.
- Create a non-root user, owning `/data`, and run as it.
- `EXPOSE 8000`.
- `HEALTHCHECK`: a `python3 -c "..."` one-liner using `urllib.request` to `GET /api/health` and
  fail on a non-200 response or a connection error. No extra OS package (e.g. no `curl`).
- `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

## `.dockerignore`

Excludes from the build context: `node_modules`, `dist`, `.venv`, `.env`, `data`, `.git`,
`list_models.py`.

## `docker-compose.yml`

One service, built from the root `Dockerfile`:
- `env_file: .env`
- port mapping `8000:8000`
- a named volume mounted at `/data` (holds the SQLite file across restarts)
- `restart: unless-stopped`

## Behaviour

With a `.env` filled in with placeholder `GATEWAY_URL`/`API_KEY` (so gateway calls fail),
`docker compose up --build`:
- starts the container without crashing
- `GET /api/health` returns 200
- `GET /` serves the dashboard
- the failing gateway calls show as red per model/family in the dashboard, not as a crash or a
  blank page

## CI (`.github/workflows/ci.yml`)

Triggers on push and on pull request. Jobs:
- backend: install `backend/requirements-dev.txt`, run `pytest` in `backend/`
- frontend: `npm ci` and `npm run build` in `frontend/` (type-checks as part of the build),
  then `npm test`
- image: `docker build .` from the repo root

## README

Adds a Docker Compose quick start:
1. `cp .env.example .env`, fill in `GATEWAY_URL` and `API_KEY`
2. `docker compose up --build`
3. open `http://localhost:8000`

Configuration is documented via a table, or a link to the existing `.env.example` comments —
not duplicated in full.
