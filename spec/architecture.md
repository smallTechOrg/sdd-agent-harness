# Architecture

> Generic, every-project stack rules (model-naming, DB driver, dev port, real-key test rule) live in `harness/patterns/tech-stack.md`. The agent graph lives in [`agent.md`](agent.md). This file is the HOW: system design, the privacy boundary, the plan-then-execute flow, the step-cap cost guard, cost accounting, and the local file store.

---

## System Overview

A single-origin local web app. A FastAPI backend serves a Next.js static export at `http://localhost:8001/app/` and exposes a small JSON API. The user uploads CSV files (stored on local disk), then asks plain-language questions. Each question runs through a LangGraph **plan-then-execute** agent: the agent drafts an analysis plan, executes it step by step as locally-run DuckDB/pandas code, and synthesises a written answer with key numbers and a result table. App state — datasets, questions, per-step audit rows (code + result), and cost records — lives in SQLite via SQLAlchemy + Alembic. The defining property is the **privacy boundary**: the LLM only ever receives the column schema plus a bounded number of sample rows; the full dataset is read and computed entirely locally and never sent to the model.

## Component Map

```
Browser (Next.js static export @ /app)
    │  JSON over HTTP (single origin :8001)
    ▼
FastAPI (src/api)  ──────────────►  SQLite (src/db)  app state/history/audit/cost
    │                                   ▲
    ▼                                   │ persist plan, steps(code+result), cost
LangGraph plan-then-execute agent (src/graph)
    │  schema + N sample rows ONLY            ┌──────────────────────────┐
    ├───────────────────────────────────────►│  Gemini Flash (network)  │
    │  ◄── plan / generated code / answer ────└──────────────────────────┘
    ▼  generated SQL/pandas code
Local Analysis Engine (src/analysis: DuckDB + pandas)
    │  runs code over the FULL dataset, returns BOUNDED aggregates only
    ▼
Local File Store (data/uploads/*.csv)  ◄── the user's raw data; never leaves the machine
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (`frontend/`) | Next.js static export: upload, question box, answer/plan/code/cost views, charts (P3), library/history (P4). |
| API (`src/api`) | FastAPI routes; upload CSV, ask question, fetch answer payload, list datasets/history/cost. `ok`/`api_error` envelope. |
| Agent (`src/graph`) | LangGraph plan-then-execute graph + runner; orchestrates plan → execute → replan → synthesize under the step cap; accumulates cost. |
| Analysis engine (`src/analysis`) | Local DuckDB/pandas: load CSV, extract schema + sample rows, run LLM-generated code over full data, return bounded aggregates; profile a dataset. |
| LLM (`src/llm`) | `LLMClient` + `GeminiProvider` (Flash). Returns text + token usage for cost accounting. |
| Storage (`src/db`) | SQLAlchemy models + SQLite; Alembic migrations. App state, audit trail, cost. |
| Local file store | `data/uploads/` — raw CSVs on disk. |
| Observability (`src/observability`) | structlog structured events per run (request, plan, each step, latency, tokens, error). |

## Data Flow (ask a question — the Phase 1 core path)

1. **Trigger:** user uploads a CSV → `POST /datasets`. The file is saved to `data/uploads/<dataset_id>.csv`; a `datasets` row records path, row/column counts, and the extracted schema. Raw rows are not loaded into the LLM at any point.
2. User asks a question → `POST /questions` with `dataset_id` + `text`. A `questions` row is created; the agent runner is invoked.
3. **plan:** the agent sends the LLM only the **schema + ≤ N sample rows** (default N from settings) and the question, and gets back a short ordered plan plus the first analysis step's code. Token usage is recorded.
4. **execute_step:** the generated SQL/pandas code runs in the local analysis engine against the **full** dataset via DuckDB. The engine returns a **bounded aggregate** (capped rows/size). The code + result is persisted as an `analysis_steps` row. No full rows go back to the LLM.
5. **step_cap_check / replan:** if the plan needs another step and the step count is under the cap, the agent loops (optionally asking the LLM for the next step's code, given prior step *results* — which are bounded aggregates, never raw rows). If the cap is hit, it stops and flags a `cost_guard` warning.
6. **synthesize_answer:** the LLM writes the plain-language answer + key numbers from the bounded step results.
7. **Output:** the `questions` row is finalized (answer, status); a `cost_records` row sums tokens in/out and the estimated USD. `GET /questions/{id}` returns the full payload: answer, key numbers, result table, plan, each step's code+result, and cost.

## Privacy Boundary

The single most important architectural constraint. **The LLM never sees full data rows.**

- **What the LLM sees:** the column schema (name + inferred type per column) and at most `AGENT_SAMPLE_ROWS` (default 10) sample rows, plus the user's question and the *bounded aggregate results* of prior steps. Sample rows are a fixed small slice, never the whole file.
- **What runs locally:** the LLM emits **SQL** (executed by DuckDB directly over the CSV via `read_csv_auto`) or **pandas** code; the analysis engine runs it on the **full** dataset on the local machine. Only aggregated/bounded results (capped at `AGENT_MAX_RESULT_ROWS`, default 1000) are returned to the agent and surfaced to the user.
- **Enforcement:** the agent layer constructs LLM payloads exclusively from `schema`, `sample_rows`, and prior `step_result` aggregates — there is no code path that places a full DataFrame or full CSV content into an LLM call. A Phase 1 test asserts the constructed payload contains no row beyond the sample set.
- **Why correctness holds:** because the code runs over the full file (not a sample), answers are exact — the failure mode of cloud chatbots silently sampling large files is structurally avoided.

## Plan-Then-Execute Flow

Implements the **Planning (#6) + LLM-Generated Code Execution (#22) + Tool Use (#5)** patterns from `harness/patterns/agentic-ai.md`, above the base ReAct floor. The planner drafts an explicit ordered strategy; the executor runs each step as generated code against the local engine; results feed the next step or the final synthesis. The full node/edge/state design is in [`agent.md`](agent.md).

## Step-Cap Cost Guard

Cost is a top priority. A hard cap (`AGENT_MAX_STEPS`, default 5) bounds the number of execute/replan iterations per question. The graph tracks `step_count` in state; the `step_cap_check` edge routes to `synthesize_answer` once the plan is satisfied **or** the cap is reached. When the cap is reached with the plan incomplete, the agent synthesises a best-effort answer **and** sets a `cost_guard_warning` so the UI tells the user "I hit the step limit — here's my best answer so far" rather than spending freely. The Flash-tier model is the default for low per-token cost.

## Cost Accounting

Every LLM call returns token usage (input/output). The runner accumulates `tokens_in`/`tokens_out` across all nodes for a question and computes an estimated USD via configurable per-1M-token Flash prices (`AGENT_PRICE_IN_PER_M`, `AGENT_PRICE_OUT_PER_M`). A `cost_records` row is written per question. The per-question cost is shown in Phase 1; the running **daily total** (sum over today's `cost_records`) is exposed in Phase 4 (`GET /cost/daily`).

## Local File Store

Uploaded CSVs are written to `data/uploads/<dataset_id>.<ext>` on local disk (alongside the SQLite DB in `data/`). The `datasets` table stores the path; DuckDB reads directly from the file via `read_csv_auto` so a 100MB file is never fully loaded into Python memory for SQL aggregates (pandas is used only for steps that genuinely need it, on bounded selections where possible). Files persist across restarts; the managed library UI (list/delete) lands in Phase 4.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini (Flash) | Plan, generate analysis code, synthesise answers, suggest follow-ups | Question fails with a surfaced error; graph `handle_error` sets status `failed`; no crash. Retry is added in the resilience hardening. |
| DuckDB | Run SQL over the full local CSV | Code error captured per-step; agent can replan or surface the error. |
| pandas | Steps needing dataframe ops; CSV/Excel parsing | As above. |
| SQLite (local file) | App state, audit trail, cost | App-level error; local, effectively always available. |

## Stack

> Locked at intake. Generic every-project rules are in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12+
- **Agent framework:** LangGraph (already wired in the skeleton; plan-then-execute graph per [`agent.md`](agent.md))
- **LLM provider + model:** Google Gemini, Flash tier for low cost. Default model `gemini-2.5-flash`, override via `AGENT_LLM_MODEL`. Key in `.env` as `AGENT_GEMINI_API_KEY`.
- **Backend:** FastAPI, single-origin, served via `uv run python -m src` on port 8001 (uvicorn target `api:app`).
- **Database + ORM:** SQLite (the production driver here IS SQLite — gates run against SQLite) + SQLAlchemy 2.0 + Alembic.
- **Local analysis engine:** DuckDB + pandas (full data processed locally; data never leaves the machine).
- **Frontend:** Next.js 15 static export (`output: 'export'`, `basePath: '/app'`), React 19, Tailwind v4, mounted by FastAPI at `/app`.
- **Dependency management:** uv + `pyproject.toml` (Python); pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | current | Agent graph orchestration |
| google-genai | current | Gemini client (token usage for cost) |
| duckdb | current | SQL over local CSV (full-data, streaming reads) |
| pandas | current | DataFrame ops + Excel parsing |
| openpyxl | current | Simple `.xlsx` reading (Phase 4 Excel) |
| sqlalchemy | 2.0.x | ORM |
| alembic | current | Migrations |
| fastapi / uvicorn | current | API + server |
| structlog | current | Structured observability events |
| @playwright/test | current | Frontend E2E smoke (required gate) |
| recharts (or Plotly-react) | current | Interactive charts (Phase 3) — see [`ui.md`](ui.md) |

> **Assumed:** charts use **Recharts** (React-native, lightweight, supports hover/zoom/filter via brush) for the Phase 3 interactive charts. Swap to Plotly only if a richer interaction set is later required.

**Avoid:** sending any full data rows to the LLM (privacy boundary); loading a whole 100MB CSV into a pandas DataFrame when a DuckDB SQL aggregate suffices; PostgreSQL/Node-server runtimes (local-first, SQLite + static export only); a hardcoded op-list interpreter instead of LLM-generated code (anti-pattern #22).

## Deployment Model

Local-first. The user runs `cd frontend && pnpm build` once, then `uv run python -m src` from the repo root, and opens `http://localhost:8001/app/`. No cloud, no auth, no server deployment. The only network egress is the Gemini API call (schema + sample rows + question only).
