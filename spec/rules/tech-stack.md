# Tech Stack

Filled in by the researcher at intake. Defaults below apply to Python projects.
Override any line — the researcher proposes, the user approves.

---

## Language

**Python 3.12+** with `uv` as package manager.

## Agent Framework

**LangGraph** — analyst loop with tool nodes (query_data, summarise, plot).

## LLM Provider

**Provider:** google (Gemini)  
**Model:** `gemini-2.5-flash`  
**Env var:** `ANALYST_LLM_MODEL` (default: `gemini-2.5-flash`)  
**API key env var:** `GEMINI_API_KEY`

Stub mode: `ANALYST_LLM_PROVIDER=stub` — all tests run offline without a real key.

## Backend Framework

**FastAPI** — async, typed, port 8001.

## Database

**DuckDB** (local file: `data/analyst.duckdb`).  
No separate DB process. DuckDB reads CSV, Excel, JSON, Parquet natively.

Tables:
- `datasets` — registered dataset metadata (name, path, schema)
- `sessions` — conversation history keyed by session_id
- `audit_log` — every SQL execution: timestamp, session_id, query_text, rows_affected, duration_ms

## Frontend

**Next.js 15** (thin shell, port 3000) — renders Plotly charts, Markdown tables, plain text.

## Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| fastapi | latest | HTTP layer |
| pydantic-settings | latest | config |
| langgraph | latest | analyst agent loop |
| duckdb | latest | data storage + query engine |
| google-generativeai | latest | Gemini 2.5 Flash |
| plotly | latest | chart spec generation |
| openpyxl | latest | Excel file support |
| pytest + pytest-asyncio | latest | tests |

Add project-specific libraries here at intake.

## What to Avoid

- SQLite as a test substitute for PostgreSQL
- Hardcoded model names (use env var)
- `git add -A` or committing `.env`
- Dev-only DB drivers (`psycopg2-binary` must be in `[project.dependencies]`)

---

## Permanent Rules

### Port: 8001

`src/__main__.py` starts on port **8001**. README and `.env.example` reference `http://localhost:8001`.

### DB driver in production dependencies

DB driver (`asyncpg`, `psycopg2-binary`) must be in `[project.dependencies]`, never dev-only.

### Tests use the same DB as production

Phase 2 gate must pass using PostgreSQL — not SQLite. `conftest.py` creates and tears down the test DB automatically.

### Phase 2 must pass with no API key

`APPNAME_LLM_PROVIDER=stub` must be set by default. The stub runs offline. Phase 2 gate fails if it requires a real API key.
