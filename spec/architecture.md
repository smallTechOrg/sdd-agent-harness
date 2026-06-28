# Architecture

> System design for the Personal Data Analysis Agent. Product intent lives in `roadmap.md`; the agent graph lives in `agent.md`. This file owns the HOW: stack, request flow, the DuckDB/SQLite split, the privacy boundary, local code execution, progress, cost, and the 100MB/<30s approach.

---

## System Overview

A single-origin, single-user local web app. The FastAPI backend (port 8001) serves the built Next.js static export at `/app/` and exposes a small JSON API. The user uploads a file; the backend ingests it into a local **DuckDB** analysis engine (and a parquet copy under `data/`). When the user asks a question, a **LangGraph** code-execution loop plans the analysis, asks **Gemini** to write pandas/SQL code, runs that code **locally on the full dataset** via DuckDB/pandas, revises on error, then summarizes and selects a chart. App state (datasets, runs, cost, conversation, sessions) lives in **SQLite via SQLAlchemy**. The LLM only ever sees schema + a tiny sample + small aggregates — never bulk rows.

## Component Map

```
Browser (Next.js static export @ /app/)
    │  JSON over HTTP (POST /datasets, POST /analyses, GET /analyses/{id} ...)
    ▼
FastAPI (src/api)  ──────────────►  LangGraph runner (src/graph/runner.py)
    │                                     │
    │                                     ▼
    │                          Agent nodes (src/graph/nodes.py)
    │                                     │  schema + sample + aggregates only
    │                                     ▼
    │                              LLMClient ──►  Gemini API (code + prose)
    │                                     │
    │                                     ▼
    │                       Analysis engine (src/analysis/engine.py)
    │                          runs generated code LOCALLY on full data
    │                                     │
    ▼                                     ▼
SQLite app state                   DuckDB + parquet (data/)
(src/db, SQLAlchemy)               FULL dataset — never sent to LLM
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (`src/api`) | HTTP contract, request/response envelopes, file upload handling, run orchestration entry |
| Agent graph (`src/graph`) | The LangGraph code-execution loop: plan → generate code → execute → revise → summarize → select chart |
| LLM (`src/llm`) | Provider-agnostic `LLMClient` wrapper over Gemini; returns text + usage (tokens) |
| Analysis engine (`src/analysis`) | Local execution of generated pandas/SQL on the FULL dataset via DuckDB; schema/sample/profile extraction; cost accounting; on-disk storage |
| App state (`src/db`) | SQLAlchemy 2.0 models + SQLite session/engine; datasets, runs, cost, sessions, conversation |
| Observability (`src/observability`) | structlog structured logging — one log line per analysis run (run_id, dataset_id, latency, tokens, cost, status) |
| Frontend (`frontend/`) | Next.js static export: upload, question, answer panel, Plotly chart, code/transparency/cost panels |

## Data Flow

**Upload (`POST /datasets`):**
1. Trigger: user drops a CSV/Excel file in the browser.
2. FastAPI streams the file to `data/uploads/{dataset_id}.{ext}`.
3. Analysis engine loads it into a DuckDB table `ds_{dataset_id}` and writes a parquet copy `data/parquet/{dataset_id}.parquet` (columnar, fast re-reads).
4. Engine extracts **schema** (column names + dtypes), a **sample** (≤20 rows), and row count.
5. A `datasets` row is written to SQLite (id, name, path, schema JSON, row_count, created_at).
6. Output: `{ dataset_id, name, schema, sample, row_count }` — the sample shown to the user IS the same sample the LLM may see (transparency by construction).

**Analyze (`POST /analyses`):**
1. Trigger: user submits a question for a dataset.
2. A `runs` row is created (status `running`); `run_agent(question, dataset_id, ...)` invokes the LangGraph graph.
3. `profile` node loads schema + sample + (Phase 2+) profile for the dataset — **this is the only dataset-derived context built for the LLM**.
4. `plan` node (Gemini) decides simple-vs-multi-step and outlines the approach.
5. `generate_code` node (Gemini) emits a self-contained pandas/SQL snippet that reads the full DuckDB table and assigns a `result` dataframe + scalar key numbers.
6. `execute_locally` node runs that code **in-process on the full data** (DuckDB/pandas) and captures the result, stdout, and any exception. **No bulk rows go back to the LLM** — only the small aggregated `result` (capped, e.g. ≤200 rows / ≤50 KB serialized).
7. On error → `revise` (loop back to `generate_code` with the traceback) up to `MAX_REVISIONS` (default 2); on repeated failure → flagged best-guess showing what was tried.
8. `summarize` node (Gemini) turns the small result into prose + key numbers. `select_chart` node picks a chart spec from the result shape.
9. Runner records tokens/cost, writes the `runs` row (question, generated code, result JSON, chart spec, llm_payload, tokens, cost, status, timings), emits a structured log line.
10. Output: answer prose, key numbers, chart spec, summary table, exact code, exact LLM payload, cost/tokens.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API | Code generation + summarization + chart selection | Node sets `state["error"]`; runner marks run `failed`, surfaces a clear message; retry/backoff on transient 429/5xx (3 attempts) |
| DuckDB (embedded) | Local execution of generated code on the full dataset | In-process; on engine error the run is marked failed with the captured exception shown to the user |

There are no network dependencies other than Gemini. DuckDB and SQLite are embedded/local.

## DuckDB (analysis) vs SQLite (app state)

These are deliberately separate engines that never share a connection:

- **SQLite via SQLAlchemy** (`src/db`) — durable *application* state only: datasets metadata, runs, cost log, sessions, conversation, notes, saved datasets, library. Small rows, transactional, migrated by Alembic. URL: `sqlite:///./data/agent.db` (the skeleton default).
- **DuckDB** (`src/analysis/engine.py`) — the *analysis compute* engine: holds the full uploaded data as tables, runs generated SQL/pandas locally, is fast on 100MB columnar data. **Not** an SQLAlchemy model — a dedicated DuckDB connection (one persistent file `data/analysis.duckdb`, or per-dataset attach) owned by the analysis layer. App state never lives in DuckDB; analysis data never lives in SQLite.

This keeps the privacy boundary and the migration story clean: Alembic only ever migrates SQLite; DuckDB tables are derived from files on disk and can be rebuilt from `data/parquet/`.

## Privacy boundary — the single redaction point

The boundary is enforced in **one place**: `src/graph/nodes.py` builds the LLM context exclusively from `make_llm_context(dataset_id)` in `src/analysis/engine.py`, which returns ONLY:
- column names + dtypes (schema),
- ≤ `SAMPLE_ROWS` (default 20) sample rows,
- the small aggregated `result` from a prior execution (capped to `MAX_RESULT_ROWS`/`MAX_RESULT_BYTES`).

No node ever passes a full dataframe, a file path's contents, or raw rows beyond the sample to `LLMClient`. The exact assembled context is stored on the `runs` row as `llm_payload` and returned to the UI verbatim (transparency panel). A Phase-1 automated test asserts that for a large fixture, the serialized `llm_payload` byte-size is bounded and contains none of the bulk rows (e.g. a sentinel value present only in row 100k never appears in any LLM payload).

## Local code execution model (Phase 1, single trusted user)

Generated code runs **in-process** in a constrained execution context — appropriate because the only caller is the local owner analysing their own data (not untrusted input):

- `execute_locally` builds a restricted namespace: `{"pd": pandas, "duckdb": con, "df": <full frame loaded from DuckDB/parquet>}` and a small set of allowed helpers. The generated snippet must assign `result` (a DataFrame or scalar) and optionally `key_numbers` (a dict).
- Execution uses `exec(compiled_code, namespace)` with: a wall-clock **timeout** (default 25s, enforced via a worker thread/process with a deadline), import restriction (a guard that rejects `import os/sys/subprocess/socket/open(` patterns at the static-check step before exec), and stdout capture.
- Full data is loaded once per dataset via DuckDB → pandas (`con.execute("SELECT * FROM ds_..").df()`), or the snippet runs as DuckDB SQL directly for large aggregations (preferred for 100MB — push the work into DuckDB rather than materializing a 100MB pandas frame).
- The captured `result` is truncated to the privacy caps before anything returns to the LLM.

> **Assumed:** Phase 1 uses an in-process restricted `exec` with a static import denylist + timeout, NOT a container/gVisor sandbox. This is explicitly justified by the single-trusted-local-user constraint in `roadmap.md`; a hardened sandbox is out of scope and would over-build the smallest win. The denylist + timeout + "prefer DuckDB SQL" approach is the realistic Phase-1 posture.

## Streaming / progress mechanism

- **Phase 1:** discrete staged progress. `run_agent` writes a `stage` field on the `runs` row as it advances (`planning → coding → running → charting → done`); the frontend polls `GET /analyses/{id}` (short interval) and renders the stage. No SSE in Phase 1 (keeps the static-export integration risk to zero on the first win).
- **Phase 3:** real streaming via **SSE** (`GET /analyses/{id}/stream`, `text/event-stream`). SSE is chosen over WebSockets because it is one-directional (server→client), trivially compatible with the FastAPI + static-export single-origin model, and needs no extra client library (browser `EventSource`). The `summarize` node streams answer chunks; stage + cost events interleave.

## Cost / token accounting

- `LLMClient.call_model` returns text **and** usage (`prompt_tokens`, `completion_tokens`) from the Gemini response metadata.
- `src/analysis/cost.py` holds a per-model price table (input/output $ per 1k tokens, env-overridable) and computes a per-run cost estimate by summing every node's LLM call.
- The runner accumulates tokens/cost across all nodes in a run and writes them to the `runs` row; the response carries `{tokens_in, tokens_out, cost_estimate}`.
- Phase 3 adds the `cost_log` daily rollup endpoint.

## 100MB / <30s performance approach

- Ingest once to **parquet + DuckDB**; never re-parse the CSV per question.
- **Push aggregation into DuckDB SQL** where possible (DuckDB is columnar, vectorized, and handles 100MB aggregations in well under a second) rather than loading a full pandas frame. The `generate_code` prompt instructs the model to prefer DuckDB SQL for heavy aggregation and use pandas only for the small result.
- The dominant cost is LLM latency (a few seconds per node), not the data scan — keeping nodes to the cheap Gemini tier and capping revisions at 2 keeps the happy path well under 30s.
- Execution timeout (25s) guards pathological generated code.

## Stack

> Concrete choices for THIS project. Generic stack rules (model-naming, DB driver in `[project.dependencies]`, dev port, real-key tests) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12+
- **Agent framework:** LangGraph (the skeleton's compiled `agentic_ai` StateGraph, extended in place)
- **LLM provider + model:** Google **Gemini** (key `AGENT_GEMINI_API_KEY` already set). `AGENT_LLM_MODEL` env-configurable.
  > **Assumed:** default model `gemini-2.5-flash` for all nodes (code-gen, summarize, chart-select) — cheapest tier that handles code generation well, matching the keep-cost-low goal. Escalation to a stronger model is an env override, not a default. Model id is read from settings, never hardcoded.
- **Backend:** FastAPI (port 8001), single-origin serving of the Next.js static export at `/app/`
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (app state) — `sqlite:///./data/agent.db`; Alembic for migrations
- **Analysis engine:** DuckDB (embedded) + pandas + pyarrow/parquet — local compute on the full dataset (NOT via SQLAlchemy)
- **Frontend:** Next.js 15 + React 19 + Tailwind, static export (`pnpm build` → `frontend/out/`)
- **Dependency management:** uv + `pyproject.toml` (Python); pnpm (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | latest (skeleton-pinned) | Agent graph |
| duckdb | latest | Local analysis compute on full data |
| pandas | latest | Dataframe ops in generated code |
| pyarrow | latest | Parquet read/write for fast re-reads |
| openpyxl | latest | Excel (.xlsx) ingest |
| google-genai (via existing `src/llm/providers/gemini.py`) | skeleton-pinned | Gemini LLM calls |
| sqlalchemy | 2.0 | App-state ORM |
| alembic | latest | SQLite migrations |
| structlog | skeleton-pinned | Structured run logging |
| react-plotly.js + plotly.js | latest | Interactive charts (zoom/hover/filter) in the static export |

**Avoid:**
- Sending bulk dataset rows to the LLM (privacy boundary).
- Putting analysis data in SQLite or app state in DuckDB (keep the two engines separate).
- A hardcoded op-list interpreter for questions — always generate executable code (anti-pattern per `harness/patterns/agentic-ai.md` #22).
- PostgreSQL/Postgres driver — intake fixed SQLite for app state; do not substitute.
- WebSockets for progress — SSE is sufficient and simpler with the static-export origin.

## Deployment Model

Long-running local process started by the documented command `uv run python -m src` (uvicorn on `0.0.0.0:8001`). The browser app is served from the same origin at `/app/`. No container, no cloud, no auth — a personal local tool. Data persists under `data/` (`agent.db`, `analysis.duckdb`, `uploads/`, `parquet/`).
