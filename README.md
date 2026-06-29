# Local Data Analyst — CSV/Excel Analysis Agent

> **All commands run from the repo root** (this directory — where `pyproject.toml` and `alembic.ini` live). There is no subdirectory to `cd` into except the explicit `cd frontend` steps below.

A personal, **local-first** data-analysis agent. Upload a CSV, ask a question in plain English, and get an analyst answer with the **exact DuckDB SQL** behind every number.

**Hard privacy boundary:** a local DuckDB engine does all data crunching; the LLM (Gemini) only ever sees the schema, column names, and aggregate result rows — **never raw data rows**. Your data stays on your machine.

## Stack

Python 3.12 · FastAPI (`api:app` @ :8001) · LangGraph · DuckDB (compute) · SQLite (app state, SQLAlchemy 2.0 + Alembic) · Next.js static export at `/app/` · Gemini `gemini-3.1-pro` · uv.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python deps + runner)
- [pnpm](https://pnpm.io/) + Node ≥ 20 (frontend build)
- A Gemini API key in `.env` (copy `.env.example` → `.env`, set `AGENT_GEMINI_API_KEY`)

```bash
cp .env.example .env
# then edit .env and set AGENT_GEMINI_API_KEY=...
```

## Setup & run

```bash
# 1. Python dependencies
uv sync --extra dev

# 2. Build the frontend (static export served by the API at /app/)
cd frontend && pnpm install && pnpm build && cd ..

# 3. Create the database tables
uv run alembic upgrade head
uv run alembic current        # must print a revision (e.g. "0002 (head)"), not blank

# 4. Start the app
uv run python -m src
```

Then open **http://localhost:8001/app/** in your browser.

## Try it

1. In the Upload panel, choose `samples/sales.csv` (a small sample is included) and click **Upload CSV**. The dataset summary (row count + columns) appears, and a **data profile** (per-column type, null/distinct counts, min/max, quality flags) is computed automatically on upload.
2. In the Question panel type a grouped question like **"What is total revenue by region?"** and click **Ask**.
3. The Answer panel shows the plain-English answer, an **Exact SQL** block with the DuckDB query that produced it, an auto-chosen **chart** (bar/line/scatter), a rich **summary table**, and 2–3 clickable **follow-up** suggestions — click one to ask it instantly. (A single-scalar question like "What is the total revenue?" shows the answer + SQL + summary, and no chart when the result isn't chartable.)

**What is real now (Phases 1–2):** upload CSV → auto-profile → ask → answer with the exact SQL, an auto-chosen chart, a rich summary table, and suggested follow-ups (clicking a follow-up asks it). Everything is computed locally in DuckDB; only schema + aggregate results ever reach the LLM.

**Clearly-labelled "Coming soon" stubs** (visible but not yet functional — not bugs): Datasets sidebar (multi-dataset compare/join), Cost meter, History/audit-trail browser, Live step stream. These — plus persistent cross-day memory, data notes, and Excel ingest — are wired up in Phase 3.

## Tests

```bash
uv run pytest                       # backend: unit + real-Gemini integration (key from .env)
cd frontend && npx playwright test  # live UI E2E (requires the app running at :8001)
```

## How it works

The question runs through a LangGraph graph: `generate_sql → execute_sql → answer → finalize`, with a **retry-on-SQL-error** edge — a DuckDB error is fed back to the model so it corrects the query (bounded retries). Only schema + aggregate result rows are ever sent to Gemini; raw rows stay in the local per-dataset DuckDB file. Every run is persisted to SQLite as an audit trail.

## Configuration (`.env`)

| Var | Purpose | Default |
|-----|---------|---------|
| `AGENT_GEMINI_API_KEY` | Gemini API key (required) | — |
| `AGENT_LLM_MODEL` | Override model | `gemini-3.1-pro` |
| `AGENT_DATABASE_URL` | SQLite app DB | `sqlite:///./data/agent.db` |
| `PORT` | Server port | `8001` |
