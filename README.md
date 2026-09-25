# LiteLLM Gateway Health Check

A dockerized FastAPI service that periodically sends a health-check prompt to every configured
model of an OpenAI-compatible (LiteLLM-like) gateway, stores the results in SQLite and shows the
availability per model family in a small React dashboard.

The full requirements live in [prompt.txt](prompt.txt). Work is tracked in GitHub issues.
