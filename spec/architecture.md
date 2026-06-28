# Architecture

## System Overview

A single-origin web application: the user's browser talks to one FastAPI process on port 8001. FastAPI serves the Next.js static export at `/app/`, handles REST and SSE endpoints under `/api/`, and houses the LangGraph agent that does all reasoning. The agent writes Python/pandas code in a sandboxed subprocess, inspects the output, and loops up to 5 times before producing a streaming answer with a Plotly chart JSON payload. All persistent state (uploaded file metadata, query runs, sessions, audit log) lives in a local SQLite database.

## Component Map

```
Browser (Next.js static export at /app/)
    │  multipart upload         SSE stream
    ├──────────────────────────────────────────► FastAPI (port 8001)
    │                                                │
    │                                          ┌─────┴────────────┐
    │                                          │  LangGraph Agent  │
    │                                          │  ┌─────────────┐  │
    │                                          │  │ profile_data│  │
    │                                          │  │ plan_steps  │  │
    │                                          │  │ execute_code│─────► Sandboxed subprocess
    │                                          │  │inspect_result│  │    (pandas + DuckDB)
    │                                          │  │synthesize   │  │
    │                                          │  └─────────────┘  │
    │                                          └─────────┬─────────┘
    │                                                    │
    │◄───────────── SSE tokens + chart JSON ─────────────┘
    │
    └── SQLite DB ← (uploaded_files, query_runs, sessions, audit_log)
         (local file, aiosqlite driver)
         Gemini 2.5 Flash (external, HTTPS)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **Frontend** | Single-page UI: file sidebar, chat panel, Plotly chart renderer, collapsible code accordion, cost footer. Built as Next.js static export, served by FastAPI at `/app/`. |
| **API** | FastAPI routes: file upload, SSE query stream, file list, session list, audit log. Input validation via Pydantic models. |
| **Agent / Graph** | LangGraph graph orchestrating multi-step reasoning: profile, plan, execute, inspect, loop or synthesize. |
| **Tools** | `profiler` (pandas column introspection), `code_executor` (sandboxed subprocess with 30 s timeout), `multi_file` (join/compare/stack logic). |
| **LLM** | Gemini 2.5 Flash via `google-genai`; one client shared across nodes, model ID from `AGENT_LLM_MODEL`. |
| **Storage** | SQLite via SQLAlchemy 2.0 async (`aiosqlite`); Alembic migrations; raw uploaded files stored in `uploads/` on the local filesystem. |
| **Observability** | structlog; per-query structured event with question, answer, tokens, cost, timing emitted to stdout. |

## Data Flow

1. **Trigger (file upload):** User selects a CSV (or Excel in Phase 3) file in the browser. `POST /api/files/upload` receives the multipart body, saves the file to `uploads/<file_id>/`, runs the profiler, writes a row to `uploaded_files`, and returns the profile JSON.
2. **Trigger (NL query):** User types a question and presses Enter. The frontend opens an SSE connection to `POST /api/query/stream` with `{question, file_ids, session_id}`.
3. **Agent execution:** The LangGraph runner initialises `AnalysisState` and calls `profile_data` (loads cached profile), then `plan_steps` (LLM call: produce a pandas/DuckDB plan), then enters the code-execution loop:
   - `execute_code`: writes a Python script to a temp file, runs it in a subprocess with a 30 s timeout, captures stdout/stderr.
   - `inspect_result`: LLM call: assess whether the output is correct and complete.
   - `decide_continue` edge: if incomplete and iterations < 5, back to `plan_steps` with revised context; else continue to `synthesize_answer`.
4. **Streaming output:** `synthesize_answer` produces a plain-text narrative + Plotly chart spec JSON. The SSE runner streams text tokens as `data: {"type":"token","text":"..."}` events, then emits a final `data: {"type":"chart","plotly":{ ... }}` event followed by `data: {"type":"cost","tokens":N,"cost_usd":X}`.
5. **Persistence:** A `query_runs` row is written with status, token counts, cost, and timing. In Phase 2, an `audit_log` row is added.
6. **Output:** Browser renders streamed text, then renders the Plotly chart client-side and shows the collapsible code accordion.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini 2.5 Flash API | LLM for planning, code generation, result inspection, answer synthesis | Retry up to 3 times with exponential back-off; after 3 failures set `state.error` and stream an error event to the browser |
| Local filesystem (`uploads/`) | Store raw uploaded files | If write fails, return HTTP 500 with a clear error; no partial state written to DB |
| SQLite (`data_analysis.db`) | Persist file metadata, query runs, sessions, audit log | On DB write failure, log the error and continue — query result is still streamed to the user (degraded: no history) |

## Stack

> This project's concrete technology choices. The generic rules (model-naming, DB driver, dev port, test environment) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12
- **Agent framework:** LangGraph (multi-step conditional loop with up to 5 code-execute iterations)
- **LLM provider + model:** Google Gemini via `google-genai`; default model `gemini-2.5-flash`; configurable via `AGENT_LLM_MODEL`
- **Backend:** FastAPI 0.115+ with `uvicorn[standard]`; SSE via `fastapi.responses.StreamingResponse`
- **Database + ORM:** SQLite via SQLAlchemy 2.0 async (`aiosqlite`); Alembic for migrations
- **Frontend:** Next.js 15 static export (`output: 'export'`, `basePath: '/app'`), React 19, Tailwind CSS v4
- **Dependency management:** `uv` + `pyproject.toml` (Python); `pnpm` + `package.json` (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| `langgraph` | ≥0.1 | Agent graph orchestration |
| `google-genai` | ≥2.9.0 | Gemini LLM client |
| `pandas` | ≥2.2 | Data profiling and in-process analysis |
| `duckdb` | ≥1.0 | Fast SQL queries over CSV/Excel for large files in the subprocess |
| `plotly` | ≥5.22 | Chart spec generation (JSON serialised, rendered client-side) |
| `aiosqlite` | ≥0.20 | Async SQLite driver |
| `structlog` | ≥24.1 | Structured logging to stdout |
| `openpyxl` | ≥3.1 | Excel file reading (Phase 3) |
| `pytest-playwright` | ≥0.5 | E2E tests against the live app |
| `plotly` (npm) | ≥2.35 | Client-side chart rendering in the Next.js app |

**Avoid:**
- `exec()` / `eval()` in the main process — all user code runs in a sandboxed subprocess only.
- `psycopg2` / PostgreSQL — this project uses SQLite only.
- `asyncpg` — not applicable (SQLite only).
- Any Anthropic library — the LLM provider is Gemini; do not add `anthropic` as a dependency.
- `pnpm dev` as the test path — the single-origin path (`pnpm build` + `uv run python -m src`) is the only gate path.

## Deployment Model

Single-process local service. The user runs `uv run python -m src` from the repo root. FastAPI starts on port 8001, serves the pre-built Next.js static export at `/app/`, and handles all API calls in the same process. No Docker, no cloud deployment, no background workers in Phase 1–3.

> **Assumed:** The `AGENT_DATABASE_URL` env var defaults to `sqlite+aiosqlite:///./data_analysis.db` (relative to the working directory). If absent, the application falls back to this default.

> **Assumed:** Uploaded files are stored at `uploads/<file_id>.<ext>` relative to the working directory. This directory is created on first upload if it does not exist.

> **Assumed:** The per-query cost estimate uses a fixed rate of `$0.000125 / 1k input tokens` and `$0.000375 / 1k output tokens` (Gemini 2.5 Flash public pricing as of 2026-06). The rate constants are in `src/data_analysis/config/settings.py` and can be updated without a code change.
