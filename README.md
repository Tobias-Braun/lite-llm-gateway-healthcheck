# LiteLLM Gateway Health Check

A dockerized FastAPI service that periodically sends a health-check prompt to every configured
model of an OpenAI-compatible (LiteLLM-like) gateway, stores the results in SQLite and shows the
availability per model family in a small React dashboard.

The full requirements live in [prompt.txt](prompt.txt). Work is tracked in GitHub issues.

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
```
