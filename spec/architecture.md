# Architecture

---

## System Overview

A single-user, local-first web application. The user opens `http://localhost:8001/app/` (a Next.js static export served by FastAPI), uploads a tabular file, and asks questions in natural language. FastAPI receives the request and runs a **LangGraph** agent. The agent generates **DuckDB SQL**, executes it against a **local DuckDB engine** that holds the uploaded data, inspects the result, and produces a plain-English answer with the exact SQL shown. App state (datasets, runs, sessions, notes) lives in **SQLite** via SQLAlchemy 2.0 + Alembic. The LLM provider is **Gemini** (`gemini-3.1-pro`).

## Privacy Invariant (FIRST-CLASS)

> **HARD PRIVACY BOUNDARY — design every node around this.** DuckDB does ALL data crunching locally. The LLM (Gemini) only ever receives: the dataset **schema** (table name, column names, column types), small **aggregate/result rows** returned by a query, dataset **profile statistics**, and user **notes**. The LLM NEVER receives raw data rows from the source file. No node may place a `SELECT *`-style raw-row sample into a prompt. This is enforced structurally: the only path from data to the LLM is via DuckDB query *results*, and a test asserts the analysis prompt contains no raw-row content. Any query the agent runs to inspect data for itself stays local and its rows are never forwarded to the LLM verbatim — only schema/aggregates are.

## DuckDB Dialect Pin (FIRST-CLASS)

> **All generated SQL is DuckDB SQL.** The system prompt, the architecture, and the agent graph all pin DuckDB explicitly. Date/time logic MUST use DuckDB functions (e.g. `date_trunc('month', col)`, `datediff`, `epoch`, `strftime`) and MUST NEVER use SQLite idioms such as `julianday()`. On any DuckDB execution error the agent retries with the verbatim DuckDB error message fed back to the model so it can correct the query (see `agent.md`).

## Component Map

```
[Browser: Next.js static export @ /app/]
        │  POST /datasets (upload)  ·  POST /datasets/{id}/ask
        ▼
[FastAPI  api:app  @ :8001]
        │
        ├─► [Ingest]  CSV → local DuckDB file (per dataset)      ──► [DuckDB engine] (raw data, local only)
        │
        ├─► [LangGraph agent]  generate SQL → execute → answer
        │         │  schema + aggregates only          ▲ rows stay local
        │         ▼                                     │
        │   [Gemini  gemini-3.1-pro]  ◄── NO RAW ROWS ──┘
        │
        └─► [SQLite app DB] (datasets, runs, sessions, notes — audit trail)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **UI** (`frontend/`) | Upload, ask, render answer + exact SQL; later: charts, tables, profile, cost, history. Static export mounted at `/app/`. |
| **API** (`src/api/`) | REST endpoints: upload dataset, ask question, fetch run/history. Thin — delegates to ingest + graph runner. |
| **Agent** (`src/graph/`) | LangGraph graph: generate-SQL → execute-in-DuckDB → answer, with retry-on-SQL-error. Enforces the privacy boundary. |
| **Analysis engine** (`src/analysis/`) | DuckDB ingest + query execution + (later) profiling + chart-spec selection. The only component that touches raw rows. |
| **LLM** (`src/llm/`) | Provider client (Gemini, already wired). Receives schema + aggregates only. |
| **Storage** (`src/db/`) | SQLite app state via SQLAlchemy + Alembic. Per-dataset DuckDB files on disk. |
| **Observability** (`src/observability/`) | Structured logging of each request, generated SQL, latency, token usage, errors. |

## Data Flow (Phase 1 core path)

1. **Trigger:** user uploads a CSV via `POST /datasets`.
2. **Ingest:** the CSV is read into a per-dataset DuckDB file; schema (columns + types) is extracted and a `Dataset` row is written to SQLite. The summary (row count, columns) is returned.
3. **Trigger:** user submits a question via `POST /datasets/{id}/ask`.
4. **Generate SQL:** the agent sends Gemini the question + dataset schema (no rows) and gets back DuckDB SQL.
5. **Execute:** DuckDB runs the SQL locally against the dataset; the (small) result set is captured.
6. **Retry on error:** if DuckDB errors, the verbatim error + prior SQL go back to Gemini for a corrected query (bounded retries).
7. **Answer:** the agent sends Gemini the question + schema + the **result rows** (aggregates) and gets a plain-English answer; the exact SQL is attached.
8. **Persist:** a `Run` row (question, SQL, result JSON, status, tokens, timestamp) is written as the audit trail.
9. **Output:** API returns answer + SQL + result; the UI renders them.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`gemini-3.1-pro`) | Generate SQL + phrase the answer | Surfaced error to user; run marked `failed`; never fabricates a number. Retry/backoff on transient errors. |
| DuckDB (in-process) | Local query/compute engine over uploaded data | Execution errors trigger the retry-on-SQL-error loop; persistent failure → flagged failure answer. |
| SQLite (in-process) | App state + audit trail | Fatal at startup if unwritable; surfaced as 500. |

## Stack

> Concrete choices for **this** project. Generic rules (model-naming, DB driver, dev port, real-key tests) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12 (skeleton requires `>=3.11`).
- **Agent framework:** LangGraph (multi-step reasoning with conditional retry edges).
- **LLM provider + model:** Gemini, default `gemini-3.1-pro` (provider auto-detected from `AGENT_GEMINI_API_KEY`; already wired in `src/llm/providers/gemini.py`). Env-configurable via `AGENT_LLM_MODEL`.
- **Backend:** FastAPI (`api:app`), run via `uv run python -m src` → uvicorn on port **8001**.
- **Database + ORM:** SQLite for app state via SQLAlchemy 2.0 + Alembic (`AGENT_DATABASE_URL`, default `sqlite:///./data/agent.db`). **DuckDB** is the separate query/compute engine over uploaded data (per-dataset files).
- **Frontend:** Next.js (static export to `frontend/out`, mounted at `/app/`).
- **Dependency management:** uv + `pyproject.toml`.

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | >=0.1 | Agent graph (already present) |
| google-genai | >=2.9.0 | Gemini client (already present) |
| fastapi / uvicorn | >=0.115 / >=0.30 | API + server (already present) |
| sqlalchemy / alembic | >=2.0 / >=1.13 | App state + migrations (already present) |
| structlog | >=24.1 | Structured observability logging (already present) |
| **duckdb** | **>=1.1** | **Local query/compute engine — ADD to dependencies (Phase 1)** |
| **openpyxl** | **>=3.1** | **Excel ingest — ADD to dependencies (Phase 3)** |

**Avoid:** sending raw data rows to the LLM (privacy invariant); SQLite as a substitute for the DuckDB compute engine; any SQLite-dialect date function (`julianday()` etc.) in generated SQL; introducing a `src/<package>/` layer — the package is `src/` directly with bare imports (`from config.settings import get_settings`).

## Deployment Model

Local single-user. One process: `uv run python -m src` serves both the API and the static-exported UI at `http://localhost:8001/app/`. No cloud, no auth, no multi-tenancy. Per-dataset DuckDB files and the SQLite app DB live under `./data/`.
