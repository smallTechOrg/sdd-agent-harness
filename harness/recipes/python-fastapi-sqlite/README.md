# agent — text-transform recipe

> **All commands run from this directory** (`harness/recipes/python-fastapi-sqlite/`).

A minimal FastAPI + LangGraph + SQLite + Anthropic agent that summarises/rephrases text.
Used as a clone-and-rename baseline by generators — see `RECIPE.md`.

## Setup

```bash
cp .env.example .env
# edit .env: set AGENT_ANTHROPIC_API_KEY=<your key>
uv sync --extra dev
```

## Run migrations

```bash
uv run alembic upgrade head
uv run alembic current
```

`alembic current` must show a revision hash — blank output means no migration was applied.

## Start (with frontend)

Build the Next.js static export and serve everything from one Python process:

```bash
./build.sh
```

Open **http://localhost:8001/app/** in your browser.

Requires Node.js + pnpm for the frontend build step.

## Start (API only, no Node.js)

```bash
uv run python -m agent
```

Server listens on http://localhost:8001 (frontend at `/app` is skipped when `frontend/out/` doesn't exist).

## Smoke test

```bash
curl -s http://localhost:8001/health
# {"data":{"status":"ok"},"error":null}

curl -s -X POST http://localhost:8001/runs \
  -H "Content-Type: application/json" \
  -d '{"input_text": "Explain why the sky is blue."}'
```

## Tests

Unit tests (no API key needed):

```bash
uv run pytest tests/unit/ -v
```

Integration tests (requires `AGENT_ANTHROPIC_API_KEY` in `.env`):

```bash
uv run pytest tests/ -v
```
