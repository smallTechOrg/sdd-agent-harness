# Data Analyst Agent

A conversational data analyst: upload a CSV, ask questions in plain English, get answers and charts.

Built on FastAPI + LangGraph + DuckDB, driven by the SDD harness in `harness/`.

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js 18+ (for future UI phase)

## Quick start

```bash
cp .env.example .env        # add ANALYST_LLM_API_KEY for live LLM calls
uv sync --extra dev
uv run python -m src
# open http://localhost:8001/health
```

The server starts in **stub mode** (no LLM calls) when `ANALYST_LLM_API_KEY` is blank.
`GET /health` returns `stub_mode: true` in that case — safe for offline tests and CI.

## .env setup

All variables use the `ANALYST_` prefix (read by `src/config.py` via pydantic-settings).

| Variable | Default | Description |
|---|---|---|
| `ANALYST_LLM_PROVIDER` | `google_genai` | LLM provider (`google_genai`, `openai`, etc.) |
| `ANALYST_LLM_MODEL` | `gemini-2.5-flash` | Model name for the chosen provider |
| `ANALYST_LLM_API_KEY` | *(empty)* | API key — leave blank for stub/offline mode |
| `ANALYST_DATABASE_URL` | `sqlite+aiosqlite:///./analyst.db` | SQLAlchemy async URL for metadata spine |
| `ANALYST_DATA_DIR` | `./data` | Directory for per-dataset DuckDB files |
| `ANALYST_PORT` | `8001` | Port the server listens on |

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns `stub_mode: true/false` |
| `POST` | `/runs` | Submit a natural-language goal, get answer + chart |
| `POST` | `/upload` | Upload a CSV/JSON file — creates a dataset |
| `GET` | `/datasets` | List ingested datasets |
| `GET` | `/datasets/{id}` | Dataset detail and schema |
| `GET` | `/traces` | Run/span timeline (server-rendered, no JS) |

## Structure

```
src/        application code (FastAPI app, LangGraph agent, DuckDB tools)
tests/      unit and integration tests (offline, FakeModel-driven)
spec/       contract — FR/CR files signed off before any code changes
harness/    the method — rules, process, recipes, patterns
logs/       evidence — sessions and analysis (gitignored)
```

## Running tests

```bash
uv run pytest          # offline unit tests (no API key required)
```
