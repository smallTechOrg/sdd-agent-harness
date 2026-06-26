# Data Analysis Agent

Upload a data file, ask questions in plain English, get explainable answers with inline charts.

A single-user, local web app: drop in a CSV / TSV / TXT / JSON / Excel file and ask plain-English questions about it. A **LangGraph ReAct loop** (Google **Gemini** + **pandas**) reasons step by step — emitting pandas expressions, executing them in a sandbox, and iterating — then returns an explainable **Markdown** answer with **inline Plotly charts**. Built on the spec-driven harness in this repo: FastAPI + LangGraph + SQLite, served single-origin on port 8001.

---

## What It Does

- **Upload data** — CSV, TSV, TXT, JSON, and Excel (`.xlsx` / `.xls`). Files are parsed with pandas, deduplicated by content hash, and stored on disk as CSV + Parquet.
- **Ask in plain English** — a LangGraph `StateGraph` ReAct loop (plan → execute → finalize) reasons over your data with Gemini, runs pandas in a sandbox, and returns a Markdown answer plus a **Steps inspector** showing every action it took.
- **Inline charts** — Plotly figures the agent produces during analysis render inline in the answer.
- **Multi-turn sessions** — ask follow-ups in the same session; resume, rename, and manage past sessions; 2–3 suggested follow-up questions per answer.
- **Derived datasets** — the agent can save intermediate results as new datasets, with lineage and staleness tracking (re-derive on demand).
- **Natural-language cleaning** — describe a cleanup in plain English; preview the generated pandas (before/after counts) before applying it.
- **On-demand notes** — generate plain-language context notes for any dataset.
- **Database tab** — an ER diagram (SVG) of your data universe with inferred foreign-key edges, per-table schema, lineage, and a data preview.
- **Offline stub mode** — with no LLM key set, a stub provider auto-engages (yellow banner, canned answers) so the whole app runs offline.

---

## Stack

- **Backend:** FastAPI + uvicorn, single-origin serving the built Next.js app on port **8001**.
- **Agent:** LangGraph `StateGraph` ReAct loop (no LangChain) over a pandas sandbox.
- **LLM:** Google **Gemini** via `google-genai`. Chosen model: **`gemini-3.1-flash-lite`** (verified against the real API at the real-key gate). Alternate provider: OpenRouter. Offline fallback: a stub provider.
- **Database:** SQLite via SQLAlchemy 2.0 + Alembic. SQLite is the **production** DB for this single-user local app.
- **Frontend:** Next.js 15 + React 19 (TypeScript), static-exported to `frontend/out/` and mounted at `/app`.
- **Dependency management:** `uv` + `pyproject.toml` (Python) · `pnpm` (frontend).

The package stays `agent` with a flat `src/` layout; all env vars use the `AGENT_` prefix.

---

## Quick Start

From the repo root:

```bash
# 1. Configure — copy the template and set your Gemini key
cp .env.example .env
# edit .env: set AGENT_GEMINI_API_KEY=<your key>
#   (leave it blank to run fully offline in stub mode)

# 2. Install Python dependencies
uv sync

# 3. Run — applies migrations, builds the frontend, serves on :8001
python agent.py --run
```

Then open the UI:

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | **Data Analysis Agent UI** (Analyse + Database tabs) |
| `http://localhost:8001/health` | API health check (reports the active provider) |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

`python agent.py` (no flag) verifies your tools, `.env`, dependencies, and tests without starting the server.

---

## Database

Migrations are applied automatically by `python agent.py --run`. To apply or verify them directly from the repo root:

```bash
uv run alembic upgrade head     # apply all migrations
uv run alembic current          # show the current revision (verify tables exist)
```

The SQLite file lives at `AGENT_DATABASE_URL` (default `sqlite:///./data/agent.db`); uploaded files live under `uploads/`.

---

## Tests

Three tiers under `tests/`. The unit suite runs fully offline; the integration and e2e suites exercise the **real Gemini** API using `AGENT_GEMINI_API_KEY` from `.env`.

```bash
# Offline stub suite — no API key needed (in-memory SQLite, no network)
uv run pytest tests/unit/ -q

# Real-Gemini suite — requires AGENT_GEMINI_API_KEY in .env
uv run pytest tests/integration/ tests/e2e/ -q
```

The real-key gates are authoritative: a stubbed pass does not count. Tests run against the production SQLite driver (the unit suite uses an isolated SQLite copy, which is correct — not a substitute).

---

## Repo Layout

```
src/                ← the agent (FastAPI + LangGraph + SQLite, Gemini/OpenRouter/stub)
  api/              ← FastAPI routers (upload · datasets · ask · sessions · runs · stats · memory · health)
  config/           ← Pydantic BaseSettings (AGENT_ env prefix)
  db/               ← SQLAlchemy 2.0 models + session
  domain/           ← Pydantic request/response + read models
  graph/            ← LangGraph ReAct StateGraph: nodes, edges, runner, sandbox, pre-flight, derived, …
  llm/              ← LLMClient + providers/ (gemini, openrouter, stub, anthropic)
  prompts/          ← prompt templates (.md)
  observability/    ← structlog config
frontend/           ← Next.js static export (served single-origin by FastAPI at /app)
tests/
  unit/             ← offline stub suite (no API key)
  integration/      ← real-Gemini suite (key in .env)
  e2e/              ← golden-path + live-server smoke (real Gemini)
spec/               ← roadmap, architecture, capabilities/, data, api, ui, agent
harness/            ← engineering rules + patterns the build follows
alembic/            ← migrations  ·  alembic.ini
agent.py            ← verify setup (default); --run to migrate + build + serve on :8001
.env.example
```

---

## How This Was Built

This product was built spec-first using the harness in this repo. The spec under `spec/` is the source of truth: it defines the roadmap, architecture, agent graph, data model, API contract, and UI. The build ran phase by phase, each phase the smallest user-testable increment, gated against the real Gemini key.

To extend it, the same workflow applies (open in Claude Code):

| Skill / command | Purpose |
|-----------------|---------|
| `/zero-shot-build [idea]` | Add a new capability, spec-first, phase by phase. |
| `/zero-shot-fix [target]` | Diagnose + fix a bug, error, failing test, or spec/code drift, then verify. |
| `/zero-shot-sync [scope]` | Reconcile spec ↔ code so they match (spec wins), then verify. |

Engineering rules and patterns live in `harness/`; mandatory AI-session rules are in `harness/rules/ai-agents.md`.
