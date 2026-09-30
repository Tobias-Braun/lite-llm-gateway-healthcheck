# CLAUDE.md

LiteLLM Gateway Health Check: a dockerized FastAPI backend (`backend/`) that periodically checks
every model of an OpenAI-compatible gateway and stores the results in SQLite, plus a React
dashboard (`frontend/`) that shows the availability per model family.

- Read `docs/README.md` first and load only the documentation files you need.
- Keep changes minimal: low code volume, clear names, short comments only where they add value.
