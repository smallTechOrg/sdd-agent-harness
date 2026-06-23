# Data Analyst Agent — Token-Economical, Local-First

Upload a CSV/Excel file, ask a question in plain English, get a senior-analyst narrative plus a result table — backed by real SQL run locally on **DuckDB**, with a full persistent audit trail. Token-economical: only the schema and at most `AGENT_MAX_SAMPLE_ROWS` sample rows are ever sent to Gemini; your raw data never leaves the machine except as that capped metadata.

> **All commands below run from the repo root.**

---

## What It Does

- **Upload** a CSV or Excel file → it is ingested into a local DuckDB table and profiled (column names, types, row count, capped samples).
- **Ask** a natural-language question over a dataset → a LangGraph agent profiles the schema, asks Gemini to generate read-only SQL from schema + tiny samples only, runs that SQL locally on DuckDB, and asks Gemini to narrate the result.
- **Audit** — every question is persisted (timestamp, NL question, generated SQL, row count, duration) and is viewable + exportable in the UI; it survives restarts.
- **Local-only** — the single network egress is the Gemini call, which carries metadata (schema + capped samples/aggregates), never bulk rows.

---

## Setup

```
cp .env.example .env
# then edit .env and set your Gemini key:
#   AGENT_GEMINI_API_KEY=<your Gemini key>
uv sync
cd frontend && pnpm install
```

`AGENT_MAX_SAMPLE_ROWS` (default `5`) is the token-economy cap — the maximum number of sample rows ever sent to the LLM. The data store lives at `AGENT_DUCKDB_PATH` (DuckDB) and metadata/audit at `AGENT_DATABASE_URL` (SQLite); both persist across restarts.

---

## Run (canonical single-origin path)

From the repo root:

```
uv run alembic upgrade head
uv run alembic current        # must show 0002 (head) — verifies tables created
(cd frontend && pnpm build)
uv run python -m src          # serves on http://localhost:8001
```

Then open **http://localhost:8001/app/**.

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | **UI** — upload, ask, results, audit log |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

---

## How to Use

1. In the **Upload** panel, choose a CSV or Excel file and upload it. It appears in the **Datasets** list with its name, row count, and inferred column schema.
2. In the **Ask a question** box, select the dataset and type a question (e.g. *"What were total sales by region?"*). You get a short analyst narrative above a formatted result table with the real numbers.
3. Open the **Audit Log** panel to see a row with the timestamp, your question, the generated SQL, the row count, and the duration. Click **Export** to download it. Restart the server and the dataset and audit entries are still there.
4. The **Charts**, **Dashboards**, and **Cross-Dataset Query** cards are labelled "Coming soon" stubs (Phase 1) — they are intentionally non-functional, not bugs.

---

## Tests

```
uv run pytest tests/unit -q     # no API key needed (ingest, token-economy, audit on real DuckDB)
uv run pytest tests -q          # full suite — hits the real Gemini API using AGENT_GEMINI_API_KEY from .env
```

The token-economy test inspects the outgoing prompt to assert no more than `AGENT_MAX_SAMPLE_ROWS` rows are ever sent to the LLM.

---

## Repo Layout

```
src/                 ← backend package root (pythonpath = ["src"], top-level imports)
  __main__.py        ← entrypoint: `uv run python -m src` (uvicorn on :8001)
  api/               ← FastAPI routers: health, datasets (upload/list), ask, audit
  config/            ← Pydantic settings (duckdb_path, max_sample_rows, DB URL, LLM)
  db/                ← SQLAlchemy models (Session, Dataset, AuditLog) + session
  domain/            ← Pydantic request/response models (analysis.py: AskRequest/Response)
  graph/             ← LangGraph data-analyst agent: profile_schema → generate_sql → execute_sql → narrate
  prompts/           ← prompt templates (generate_sql.md, narrate.md)
  services/          ← ingest.py (CSV/Excel → DuckDB), duckdb_store.py, audit.py
  llm/               ← LLM provider abstraction (Gemini auto-detected from key)
  observability/
frontend/            ← Next.js static export (served by FastAPI at /app)
tests/
  unit/              ← passes with no API key
  integration/       ← requires real Gemini key in .env
alembic/versions/    ← 0001_initial, 0002_data_analyst_models
spec/                ← product spec (roadmap, architecture, capabilities, data, api, ui)
harness/             ← engineering rules and patterns
CLAUDE.md
pyproject.toml
alembic.ini
agent.py             ← alternate run helper (sets PYTHONPATH=src; --check-setup to verify)
.env.example
```

---

## Notes

- **Local-only & token-economical** by design: raw rows stay on your machine; only schema + capped samples/aggregates are sent to Gemini.
- **Read-only SQL** — the agent only runs SQL it generates from your question; non-SELECT statements are rejected. The tool never executes arbitrary user-supplied SQL and never mutates your source files.
- Default model is `gemini-2.5-flash` (override with `AGENT_LLM_MODEL`).
