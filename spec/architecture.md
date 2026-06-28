# Architecture

## System Overview

A single-user, local web application. The browser talks to a FastAPI server on port 8001;
the server stores uploaded spreadsheets on local disk (`uploads/`), persists metadata and
history in a local SQLite database, and runs a LangGraph agent that answers natural-language
questions by **writing pandas code and executing it server-side against the full dataset**.
The LLM (Google Gemini, via `google-genai`) is used only to plan, write code, and phrase
answers — it receives schema and tiny samples, never raw data rows.

## Privacy Data-Flow Boundary (NON-NEGOTIABLE)

This is the architecture-critical invariant. It also appears in [agent.md](agent.md).

**Crosses to the LLM (allowed):**
- Column names and dtypes.
- Basic per-column stats (count, min/max/mean for numerics, distinct-count / top values for
  categoricals, missing-value counts) — all **aggregates**, never row identities.
- A tiny sample: **at most 5 rows** (configurable down to 0), used to disambiguate formats.
- The user's question and prior conversation turns (which are the user's own words).
- Generated code, execution errors, and a **truncated, aggregated** result preview (e.g. the
  head of a small result table or scalar values) for the inspect/answer steps.

**Never crosses to the LLM (server-side only):**
- The full dataset / any bulk of raw rows.
- The raw file contents beyond the ≤5-row sample.

**Enforcement:**
- The LLM client is only ever called with a constructed context object built by
  `src/analysis/profile.py` (schema + stats + ≤5-row sample). Nodes never pass a full
  DataFrame to the LLM.
- The sample-row cap is a single constant (`MAX_SAMPLE_ROWS = 5`) applied in the profiler and
  asserted in tests (`tests/phase1/test_privacy_invariant.py`): the test reads what would be
  sent to the LLM and asserts row count ≤ cap and that no full-frame serialization occurs.
- Result previews passed back to the LLM for the inspect/answer step are head-truncated and
  size-capped by the same module.

## Local Code-Execution Model

The agent's core action is **LLM-generated code execution** (see [agentic-ai.md](../harness/patterns/agentic-ai.md)
pattern #22). The flow: the agent writes a pandas snippet that assigns its answer to a
well-known variable (`result`), referencing the loaded DataFrame(s) by name (`df`, and in
Phase 4 multiple named frames). `src/analysis/execute.py` runs the snippet against the
**full** in-memory DataFrame loaded from disk, captures `result` (plus stdout and any
exception), and returns a structured `ExecutionResult`.

**Safety posture (single trusted local user):** the user runs this on their own machine
against their own files; there is no untrusted-input boundary. We therefore do **not** build a
hardened sandbox. We apply pragmatic guardrails appropriate to a trusted single user:
- Execute in a restricted namespace exposing only `pd`, `np`, the named DataFrame(s), and a
  small allowlist of builtins — not the host module globals.
- A wall-clock timeout per execution (default 60s) and a hard cap on result preview size.
- Errors are captured and fed back to the refine loop, never crashing the request.

This is documented honestly: it is **not** a security sandbox for untrusted code; it is
guardrails for a trusted local operator. Encoded in [roadmap.md → Out of Scope](roadmap.md).

## Component Map

```
Browser (Next.js static export @ /app/)
        │  fetch / (Phase 3) SSE
        ▼
FastAPI (src/api) ──────────────► uploads/ (raw files on disk)
        │                                 ▲
        ▼                                 │ load full data
LangGraph agent (src/graph) ──► analysis engine (src/analysis)
        │   schema+sample only            │ profile / execute pandas / chart
        ▼                                 ▼
   Gemini (src/llm)                  pandas / numpy
        │
        ▼
   SQLite (src/db) — datasets, conversations, messages, runs, (P4) column_notes
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (`frontend/`) | Single-page workbench, served as static export at `/app/` |
| API (`src/api`) | HTTP surface: upload, ask, list, history; `ok()`/`api_error()` envelopes |
| Agent (`src/graph`) | LangGraph plan→generate→execute→inspect→refine→answer graph |
| Analysis (`src/analysis`) | profile, execute pandas, (P3) chart spec, (P2) cost, (P4) load/join |
| LLM (`src/llm`) | Gemini provider + `LLMClient` wrapper (existing) |
| Persistence (`src/db`) | SQLAlchemy 2.0 models + session; SQLite on disk |
| Storage | `uploads/` raw files; `data/agent.db` SQLite |

## Data Flow

1. **Trigger:** user uploads a file (`POST /datasets`) or asks a question (`POST /ask`).
2. **Ingest:** server saves the file to `uploads/<dataset_id>/<filename>`, loads it with
   pandas, builds a profile (schema + stats + ≤5-row sample), persists `datasets` row.
3. **Ask:** server starts an agent run (`runs` row); the graph plans, generates pandas,
   executes it against the full DataFrame, inspects the result, optionally refines, then
   phrases the answer and suggests follow-ups.
4. **Output:** the plain-English answer + generated code + plan + (P3) chart spec are returned
   and persisted on the `runs` row.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini (`google-genai`) | Plan, write code, phrase answers | Surface error to user; retry with backoff (see [agent.md](agent.md)) |
| SQLite (local file) | Persist datasets, conversations, runs | Fatal — app cannot start; surfaced at boot |
| Local disk (`uploads/`) | Store raw spreadsheets | Upload fails with a clear error if write fails |

## Stack

> Concrete choices for **this** project. Generic rules (model-naming, DB driver, dev port,
> real-key tests) live in [tech-stack.md](../harness/patterns/tech-stack.md).

- **Language:** Python 3.12 (backend), TypeScript (frontend).
- **Agent framework:** LangGraph (extends the existing `src/graph/` skeleton).
- **LLM provider + model:** Google Gemini via `google-genai`. **Default working model:
  `gemini-2.5-flash`** for cost — it handles planning, code generation, and answer phrasing
  for the common case. **Escalation (Phase 4):** route hard/ambiguous questions to
  `gemini-2.5-pro` via the difficulty router (see [agent.md](agent.md)). Model is
  env-configurable via `AGENT_LLM_MODEL`; provider auto-detected from `AGENT_GEMINI_API_KEY`
  (already wired in `src/llm/client.py`).
  > **Assumed:** baseline default is `gemini-2.5-pro` (in `GeminiProvider.DEFAULT_MODEL`); the
  > spec changes the working default to `gemini-2.5-flash` by setting `AGENT_LLM_MODEL=gemini-2.5-flash`
  > in `.env`. The Phase-1 backend slice also sets the application default to `gemini-2.5-flash`
  > when `AGENT_LLM_MODEL` is blank, so cost is low out of the box.
- **Backend:** FastAPI (existing `create_app()`), single-origin static-export mount at `/app/`.
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (existing `src/db`). **SQLite is the production
  database here** (single local user) — therefore tests run against SQLite and that is valid.
  Migrations via Alembic (`uv run alembic`).
- **Frontend:** Next.js 15 static export (`output: 'export'`, `basePath: '/app'`) + React 19 +
  Tailwind (existing baseline).
- **Dependency management:** uv + `pyproject.toml` (Python), pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | existing | Agent graph orchestration |
| google-genai | existing | Gemini LLM calls |
| fastapi / uvicorn | existing | HTTP server |
| sqlalchemy | 2.0 | ORM |
| alembic | existing | Migrations |
| pandas | add (backend slice) | Load + analyze spreadsheets |
| numpy | add (transitive/with pandas) | Numerics in execution namespace |
| openpyxl | add (Phase 4) | Read `.xlsx` multi-sheet workbooks |
| python-multipart | add (Phase 1) | FastAPI file upload parsing |
| (frontend charts) | Phase 3 | Interactive charting — generator picks (e.g. Recharts/Plotly) |

**Avoid:** sending any full DataFrame or bulk rows to the LLM; a hardcoded op-list interpreter
in place of generated code (anti-pattern per [agentic-ai.md](../harness/patterns/agentic-ai.md)
#22); SQLite-as-substitute concerns (SQLite is the real DB here); renaming the `src/` package
(imports are bare `config.settings`, `graph.agent`, etc. — keep `src/`).

## Deployment Model

Long-running local FastAPI service (`uv run python -m src` → uvicorn on `0.0.0.0:8001`).
Frontend built ahead of time (`cd frontend && pnpm build` → `frontend/out/`) and served by the
same server at `/app/`. Single process, single user, no external network exposure intended.
