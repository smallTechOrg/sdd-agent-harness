# Tech Stack

Filled in by the researcher at intake. Approved for the Data Analyst Agent build.

---

## Language

**Python 3.12+** with `uv` as package manager (>=0.5, workspace lockfile support).

## Agent Framework

**None** — hand-rolled linear node runner (`AgentRunner` in `src/agent/graph.py`). The generate→execute→finalize pipeline is a fixed 3-node sequence with a shared error terminal. LangGraph overhead is unnecessary for a linear graph. See spec/agent-graph.md.

## LLM Provider

**Provider:** anthropic
**Model:** `claude-sonnet-4-6` (configurable via `DAA_LLM_MODEL`)
**Env var:** `DAA_LLM_MODEL` — always configurable, never hardcoded.
**SDK:** `anthropic` 0.40.* with prompt caching on system prompt for token economy.
**Default:** `DAA_LLM_PROVIDER=stub` (offline, no key required for tests)

| Provider | Default model | Env var | Notes |
|----------|--------------|---------|-------|
| stub | — | `DAA_LLM_PROVIDER=stub` | offline default; no key; all phases gate here |
| anthropic | `claude-sonnet-4-6` | `DAA_ANTHROPIC_API_KEY` | Anthropic Messages API; prompt caching |

## Backend Framework

**FastAPI 0.115.*** — async, Pydantic v2 validation, multipart upload support.

## Database

**DuckDB 1.1.*** — analytics engine for uploaded tabular data (CSV/JSON/Excel/Parquet); persistent tables, not views [C-DUCKDB-VIEW].
**SQLite (aiosqlite 0.20.***)** — metadata spine; sessions, dataset registry, audit_log, conversation_message.
**No server DB** — local file only. `./data/app.duckdb` + `./data/meta.db`.

**ORM:** None for DuckDB (native driver). `aiosqlite` for SQLite directly (no SQLAlchemy — single-writer, simple schema).
**Migrations:** None — `create_tables_sqlite()` at FastAPI lifespan startup via `CREATE TABLE IF NOT EXISTS`.

## Frontend

**Next.js 15** (App Router), React 19, Tailwind CSS 3.4.x.
**Markdown:** react-markdown 9.x + remark-gfm 4.x (GFM tables — not `<pre>`) [C-MD-RENDER].
**Charts:** react-plotly.js 2.x + plotly.js 2.x (SSR-disabled dynamic import) [C-PLOTLY-SSR].
**Testing:** Playwright 1.46.x for Live-UI gate.

## Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.* | HTTP layer + file upload |
| pydantic-settings | 2.* | typed config, extra="ignore" [C-ENV-EXTRA] |
| duckdb | 1.1.* | analytics DB + CSV/JSON/Parquet ingest |
| aiosqlite | 0.20.* | async SQLite metadata spine |
| anthropic | 0.40.* | LLM SDK with prompt caching |
| pandas | 2.2.* | Excel/CSV/JSON file reading |
| openpyxl | 3.1.* | Excel (.xlsx) ingest via pandas |
| python-multipart | 0.0.20.* | FastAPI multipart upload [C-MULTIPART] |
| uvicorn | 0.30.* | ASGI server |
| pytest | 8.* | test runner |
| pytest-asyncio | 0.24.* | async FastAPI tests |
| httpx | 0.27.* | async test client for FastAPI |
| next | 15.x | frontend framework |
| react | 19.x | UI runtime |
| tailwindcss | 3.4.x | styling |
| react-markdown | 9.x | markdown table rendering |
| remark-gfm | 4.x | GFM table plugin |
| react-plotly.js | 2.x | interactive charts (SSR-disabled) |
| plotly.js | 2.x | chart rendering |
| playwright | 1.46.x | Live-UI gate |

## What to Avoid

- SQLite as a test substitute for DuckDB analytics [C-DB-SAME-AS-PROD]
- Hardcoded model names — always use `DAA_LLM_MODEL` env var [C-LLM-MODEL]
- `git add -A` — stage specific paths only [C-GIT-ADD]
- Committing `.env` or any file with real API key values
- `CREATE VIEW` in DuckDB — use `CREATE OR REPLACE TABLE` [C-DUCKDB-VIEW]
- `google-generativeai` — this build uses Anthropic SDK [C-LLM-SDK]
- `react-plotly.js` imported at top-level — use `dynamic(() => ..., {ssr: false})` [C-PLOTLY-SSR]
- Browser APIs at module/initialiser scope in Next.js — use `useEffect` [C-SSR-BROWSER-API]

---

## Permanent Rules

### Port: 8001

Backend on **:8001**. Frontend on **:3000**. README and `.env.example` reference these.

### Tests use the same DB as production

All tests run against `./data/app.duckdb` (DuckDB) + `./data/meta.db` (SQLite) — never an in-memory substitute [C-DB-SAME-AS-PROD].

### Default to stub

`DAA_LLM_PROVIDER=stub` is the default in `.env.example`. Tests enforce `ALLOW_MODEL_REQUESTS=False` in conftest.py. A green stub run proves plumbing; eval cases prove behaviour [C-STUB].

### Env prefix: DAA_

All project environment variables use the `DAA_` prefix (Data Analyst Agent). No `APP_` prefix.
