# Architecture

A personal, single-user, browser-based CSV data-analysis agent. The user uploads a CSV, asks plain-English questions, and gets plain-English answers — with a hard privacy guarantee that raw row data never leaves the machine.

---

## System Overview

One person runs this locally. A FastAPI process serves both the JSON API and the static Next.js UI on a single origin (`http://localhost:8001/app/`). The user uploads a CSV through the browser; the file is parsed and stored **locally** with pandas. To answer a question, the agent computes a compact **data profile** locally and sends only that profile plus the user's question to Gemini, which returns a plain-English answer. The full raw dataset is never transmitted to any cloud service.

## The Privacy Data Boundary (first-class architectural concern)

This is the dealbreaker constraint and the spine of the design. There are two zones:

```
┌──────────────────────── LOCAL MACHINE (trusted) ─────────────────────────┐
│                                                                          │
│  Browser UI ──upload CSV──► FastAPI ──► pandas.read_csv (local)          │
│                                  │                                       │
│                                  ▼                                       │
│                       data/datasets/{id}.csv  (raw rows on local disk)   │
│                       SQLite: DatasetRow (metadata + schema ONLY)        │
│                                  │                                       │
│   ask(question) ──► LangGraph ──► profile_dataset (pandas, LOCAL):       │
│                                   schema + row_count + per-column        │
│                                   summary stats + ≤5 truncated examples  │
│                                  │                                       │
│                                  ▼                                       │
│                       ┌───── DATA BOUNDARY ─────┐                        │
└───────────────────────│   CROSSES TO CLOUD ↓    │────────────────────────┘
                        │  • the user's QUESTION  │
                        │  • the data PROFILE     │   (small, derived;
                        │    (schema, stats,      │    NO raw rows,
                        │     tiny examples)      │    NO full DataFrame)
                        └────────────┬────────────┘
                                     ▼
                          ┌────────────────────────┐
                          │  Gemini 2.5 Flash      │  returns plain-English
                          │  (cloud LLM)           │  answer grounded in profile
                          └────────────────────────┘
```

**What NEVER crosses the boundary:** the raw CSV bytes, the full pandas DataFrame, any complete data row, any full column. **What crosses:** the natural-language question and the derived profile (column names + dtypes, row count, per-column summary statistics, and at most 5 truncated example values per column). The computed answer comes back. This boundary is enforced in code at the `build_prompt` node (it serializes only the profile, never the DataFrame) and is **asserted by an automated test** in every phase.

## Component Map

```
Browser (Next.js static export at /app/)
    │  multipart upload / JSON ask
    ▼
FastAPI (src/api) ──► routers: datasets.py (upload, ask)   ◄── single origin, no auth
    │
    ▼
Dataset store (src/datasets/store.py)        SQLite (DatasetRow: metadata + schema only)
    │  raw CSV → data/datasets/{id}.csv (LOCAL DISK)
    ▼
Profiler (src/datasets/profiler.py, pandas)  ──► DataProfile (derived, small)
    │
    ▼
LangGraph agent (src/graph) ──► Gemini 2.5 Flash (src/llm) ◄── only question + profile cross
    │
    ▼
RunRow (SQLite: question, answer, status)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| UI (Next.js static export) | Upload CSV, show schema, ask a question, show the answer; labelled stubs for Charts + Anomalies |
| API (FastAPI, `src/api`) | `POST /datasets` (upload), `POST /datasets/{id}/ask`; single origin; serves `/app` |
| Dataset store (`src/datasets/store.py`) | Write/read raw CSV on local disk; persist `DatasetRow` metadata in SQLite |
| Profiler (`src/datasets/profiler.py`) | Compute the small derived `DataProfile` locally with pandas — the only thing allowed near the LLM prompt |
| Agent (`src/graph`) | LangGraph pipeline: load profile → build token-frugal prompt → call Gemini → finalize/error |
| LLM (`src/llm`) | Gemini provider; `gemini-2.5-flash` |
| Storage (`src/db`) | SQLite via SQLAlchemy: `DatasetRow`, `RunRow` |

## Data Flow

1. **Trigger:** user uploads a CSV in the browser → `POST /datasets`.
2. FastAPI streams the file to `data/datasets/{id}.csv` (local disk); pandas parses it; the profiler derives the schema and a `DatasetRow` (metadata + schema only) is written to SQLite. Response: `dataset_id` + schema.
3. User types a question → `POST /datasets/{id}/ask`.
4. The runner starts a LangGraph run: `load_profile` (pandas re-profiles the local CSV) → `build_prompt` (serializes **only** question + profile) → `answer` (one Gemini call) → `finalize` (or `handle_error`).
5. **Output:** a plain-English answer is returned and rendered; a `RunRow` records question, answer, status.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`gemini-2.5-flash`) | Generate the plain-English answer from the profile | Request fails → status `failed`, human-readable error in the UI; no crash |
| Local filesystem (`data/datasets/`) | Store raw CSVs locally so rows never leave the machine | Missing/corrupt file → human-readable error |
| SQLite (`data/agent.db`) | Persist dataset metadata + run history | Connection error → 500 with human copy |

## Stack

> Generic every-project rules (model-naming, DB driver, dev port, real-key test rule) live in `harness/patterns/tech-stack.md`. This section is only what **this** project picked, on top of the existing skeleton.

- **Language:** Python 3.11+ (skeleton `requires-python = ">=3.11"`); bare `src` imports (`from graph.state import ...`), `pythonpath=["src"]`.
- **Agent framework:** LangGraph (skeleton's compiled `StateGraph`, extended in place).
- **LLM provider + model:** Gemini / `gemini-2.5-flash` (cheap + capable; explicitly set, NOT the skeleton's `gemini-2.5-pro` default). Key `AGENT_GEMINI_API_KEY`, auto-detected by `LLMClient`.
- **Backend:** FastAPI, single origin, serves the Next.js static export at `/app/`, port 8001.
- **Database + ORM:** SQLite (`sqlite:///./data/agent.db`) + SQLAlchemy 2.0 + Alembic. SQLite **is** the production DB for this local personal tool — there is no PostgreSQL.
- **Frontend:** Next.js 15 + React 19 + Tailwind, static export mounted at `/app`.
- **Data engine:** pandas (local CSV parsing, profiling, aggregation — the privacy enforcement layer).
- **Dependency management:** uv + `pyproject.toml` (Python); pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| pandas | >=2.2 | Local CSV parse, profile, aggregate — raw data stays local |
| langgraph | >=0.1 | Agent graph (already in skeleton) |
| google-genai | >=2.9 | Gemini provider (already in skeleton) |
| fastapi | >=0.115 | API + static serving (already in skeleton) |
| python-multipart | >=0.0.9 | File upload parsing for FastAPI multipart |
| sqlalchemy / alembic | >=2.0 / >=1.13 | ORM + migrations (already in skeleton) |

**Avoid:**
- Sending the raw DataFrame, raw CSV, or any full row/column to the LLM — violates the dealbreaker privacy rule.
- `gemini-2.5-pro` — too expensive for this cost-sensitive personal tool; use `gemini-2.5-flash`.
- LLM-generated arbitrary code execution in Phase 1 — unsafe and not first-time-right; deferred (and may be skipped entirely).
- PostgreSQL / any DB connector — out of scope; SQLite only.

## Deployment Model

Single local process started with `python agent.py --run` (applies Alembic migrations, builds the frontend, starts uvicorn on port 8001). UI at `http://localhost:8001/app/`. Single user, no auth, no network exposure beyond the local Gemini API calls.
