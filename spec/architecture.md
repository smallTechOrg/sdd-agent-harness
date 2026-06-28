# Architecture

---

## System Overview

A single-user, browser-based data-analysis agent. A Next.js frontend (static-exported and served by FastAPI at `/app`) lets the user upload a tabular file and ask plain-language questions in a session. The FastAPI backend loads the file into a server-side pandas DataFrame, runs a LangGraph agent that plans → writes pandas code → executes it locally against the full data → inspects → refines, and streams each step to the browser over Server-Sent Events. Only schema and computed aggregates ever reach the Gemini LLM — raw rows never leave the server. Every run is persisted to SQLite for a per-dataset audit trail.

## Component Map

```
Browser (Next.js static export at /app)
    │  upload / SSE ask / history (fetch)
    ▼
FastAPI (src/api/*)  ──►  DatasetStore (in-mem DataFrame cache + file store)
    │                          ▲
    ▼                          │ loads full DataFrame
LangGraph agent (src/graph/*)  │
    │  plan → gen-code → execute → inspect → refine
    ├──► CodeExecutor (src/analysis/executor.py)  — runs pandas in restricted namespace on the full DataFrame
    ├──► Profiler (src/analysis/profiler.py)      — schema + dtypes + ranges + quality flags
    ├──► LLM payload builder (src/llm/payload.py) — PRIVACY GATE: schema + aggregates only
    │         ▼
    │    Gemini (gemini-2.5-flash)  ←── sees schema + code + code output, NEVER raw rows
    ▼
SQLite (src/db) — datasets, runs, run_steps (audit history)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (Next.js) | Upload, profile view, chat session, streamed step viewer, answer card (prose/chart/table/code), cost meter, history. |
| API (FastAPI) | Upload + profile, streaming `/ask` (SSE), per-dataset history. Privacy-safe — never returns more than the user uploaded. |
| Agent (LangGraph) | The bounded plan→generate→execute→inspect→refine loop, clarify-first branch, finalize, error handling. |
| Analysis | `Profiler`, `CodeExecutor` (sandboxed pandas), `DatasetStore` (DataFrame cache + file store). |
| LLM | Provider client + the privacy payload builder that guarantees only schema/aggregates reach Gemini. |
| Storage (SQLite) | Datasets, runs, and per-step audit rows. |

## Data Flow

1. **Trigger:** user uploads a CSV via `POST /datasets`. Backend stores the file, loads it into a DataFrame in `DatasetStore`, runs `Profiler`, persists a `datasets` row, returns the profile.
2. User asks a question via `POST /datasets/{id}/ask` (SSE). A `runs` row is created; the LangGraph agent starts.
3. The agent loops: **plan** (LLM, sees schema only) → **generate code** (LLM) → **execute** (local pandas on full DataFrame) → **inspect** (LLM sees code output/aggregates only) → refine or finish. Each iteration emits an SSE step event and writes a `run_steps` row.
4. **Finalize:** the agent composes prose + picks a chart spec + builds the results table + attaches the exact code, records tokens/cost, and streams a final `answer` event.
5. **Output:** the browser renders the answer card; the run is browsable in per-dataset history.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini API (`gemini-2.5-flash`) | Planning, code generation, inspection, prose composition | Retry w/ backoff (2 tries); on persistent failure the run is marked `failed` with a surfaced error and the partial steps remain in history. |
| pandas (local execution) | Runs generated analysis code on the full dataset | Code error is caught, fed back to the agent as an inspect signal to refine (counts against step limit). |

## Existing Skeleton (extend in place — do NOT duplicate)

Generators **rename/extend** these files; they never copy or create parallel modules:

- `src/graph/state.py` — extend `AgentState` (keep `run_id`, `messages`; add analysis fields).
- `src/graph/nodes.py` — replace the `transform_text` node with the analysis nodes (`profile`, `plan`, `generate_code`, `execute`, `inspect`, `clarify`, `finalize`, `handle_error`).
- `src/graph/agent.py` / `edges.py` — rewire the graph to the loop topology in `spec/agent.md`.
- `src/graph/runner.py` — extend to a **streaming** runner that yields step events (used by the SSE endpoint) and persists `run_steps`.
- `src/db/models.py` — rename/extend `RunRow` and add `DatasetRow`, `RunStepRow`.
- `src/api/runs.py` → replaced by `src/api/ask.py`, `src/api/datasets.py`, `src/api/history.py`.
- `src/llm/client.py` + `providers/gemini.py` — extend to expose token usage; add `src/llm/payload.py` (privacy gate).
- `src/config/settings.py` — add `gemini_model`, `max_steps`, `dataset_store_dir`, `cost_per_1k_*` fields (env prefix `AGENT_`).
- `frontend/src/app/page.tsx` — replace the transform form with the analysis UI.
- New modules: `src/analysis/{profiler,executor,dataset_store}.py`, `src/prompts/{plan,generate_code,inspect,finalize,clarify}.md`.

## Stack

> Generic stack rules (model-naming, DB driver, port 8001, real-key tests) live in `harness/patterns/tech-stack.md`. This is only what **this** project picked.

- **Language:** Python 3.12 (backend), TypeScript (frontend)
- **Agent framework:** LangGraph (multi-step loop with conditional edges + bounded refinement)
- **LLM provider + model:** Google Gemini / `gemini-2.5-flash` — the cheap/fast tier; cost is a stated constraint and no node needs `pro`-tier deep reasoning. Env-configurable via `AGENT_GEMINI_MODEL`.
- **Backend:** FastAPI (REST + SSE streaming), uvicorn, port 8001
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (single local user; audit history only — no concurrent-writer needs)
- **Frontend:** Next.js 15 (static export, `basePath: '/app'`) + React 19 + Tailwind v4
- **Dependency management:** uv + pyproject.toml (Python), pnpm (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | latest | Agent graph |
| pandas | 2.x | DataFrame load + analysis execution |
| openpyxl | 3.x | Excel (.xlsx) reading |
| google-genai | latest | Gemini client (already in skeleton) |
| sqlalchemy | 2.x | ORM |
| structlog | latest | Structured request/response/step logging (already in skeleton) |
| sse-starlette | latest | Server-Sent Events for live step streaming |
| recharts | latest | Interactive charts (zoom/hover) in the frontend |
| @playwright/test | latest | E2E smoke tests |

**Avoid:** PostgreSQL (single local user — SQLite is correct here); RestrictedPython or a separate container for code execution in v1 (use a curated restricted namespace + AST allow-list — see `spec/agent.md`); shipping raw rows to the LLM under any circumstance.

## Deployment Model

Long-running local FastAPI service (`uv run python -m src`) serving the static-exported frontend at `http://localhost:8001/app/`. Single process, single user, local SQLite file and a local managed file store for uploaded datasets. No cloud deploy in scope.

## Observability

Structured logging (structlog → stdout, already in skeleton) from Phase 1: every LLM call logs model, prompt-token/completion-token counts, latency, and cost; every agent step logs node name, step index, success/error; every run logs final status and duration. Per-step rows are also persisted to `run_steps` for the in-app audit trail. LangSmith tracing is NOT used (Gemini, not LangChain-native); structured logs + DB audit rows are the observability surface and are wired in Phase 1, never deferred.
