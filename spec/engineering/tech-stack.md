# Tech Stack

## Language

**Python 3.12**

**Why:** User-specified. Best ecosystem for data manipulation (pandas) and AI/LLM libraries.

## Agent Framework

**LangGraph 0.2+** (async nodes)

**Why:** Structured state machine for the load → plan → execute → finalize pipeline. Makes error routing explicit. Nodes are `async def` so they can drive the async MCP client; the graph is invoked with `ainvoke()` inside a single `asyncio.run()` owned by the (already-backgrounded) pipeline thread.

## Tool Protocol

**Model Context Protocol (MCP)** via the **official `mcp` SDK, pinned `==1.28.0`**

**Why:** The agent's tools are formalized as MCP. Each data source is wrapped by an in-process `FastMCP` server; the agent is an MCP **client** that discovers tools with `list_tools()` and invokes them with `call_tool()`. MCP is only the agent↔tool transport — the LLM↔agent ReAct protocol stays hand-rolled.

**Transport:** in-process / in-memory (`mcp.shared.memory.create_connected_server_and_client_session`). No subprocess, no ports. This helper is semi-public and touches a private attribute, so it is isolated behind a single adapter module (`graph/mcp_pool.py`) — swapping to stdio / Streamable-HTTP / the v2 `mcp.client.Client` is then a one-file change. The exact `==1.28.0` pin is deliberate: the SDK's v2 line renames the high-level server and removes the in-memory helper.

**Use the official `mcp` SDK only** — do **not** add `langchain-mcp-adapters` or any third-party MCP wrapper.

## Data Source Query Engine

**DuckDB** queries the Parquet files directly, read-only.

**Why:** Each MCP server wraps one Parquet file and runs the LLM's `SELECT` against it via DuckDB (`read_parquet(...)`). DuckDB reads Parquet natively (no load step) and ships native `STDDEV`/`VARIANCE`, so the old pandas→in-memory-SQLite copy and the custom SQLite aggregate functions are removed. SQLite remains the **application metadata** store (below); DuckDB is only the **data-source query engine**.

## LLM Provider

**Google Gemini via `google-genai` SDK**

**Model:** `gemini-2.5-flash`

**Why:** User has a Gemini API key. `gemini-2.5-flash` is the current recommended default for Gemini as of 2026.

## Backend Framework

**FastAPI 0.115+** with **uvicorn** and **Jinja2** templates

## Database

**SQLite** via **SQLAlchemy 2.0** (sync, declarative Mapped types)

**ORM/ODM:** SQLAlchemy 2.0 + Alembic for migrations

## Frontend

**Jinja2 templates** served by FastAPI. Minimal inline CSS. No JS framework in v0.1.

React/Vite frontend deferred to Phase 4.

## Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| fastapi | ≥0.115 | HTTP framework |
| uvicorn | ≥0.29 | ASGI server |
| jinja2 | ≥3.1 | HTML templates |
| python-multipart | ≥0.0.9 | File upload parsing |
| sqlalchemy | ≥2.0 | ORM + SQLite driver |
| alembic | ≥1.13 | Schema migrations |
| pydantic-settings | ≥2.2 | Settings from env |
| langgraph | ≥0.2 | Agent graph (async nodes) |
| mcp | ==1.28.0 | Official Model Context Protocol SDK (FastMCP server + client) — pinned |
| duckdb | ≥1.1,<2 | Read-only SQL over the Parquet data sources |
| google-genai | ≥1.0 | Gemini SDK |
| pandas | ≥2.2 | CSV→Parquet ingestion + schema extraction |
| pyarrow | ≥14 | Parquet engine for pandas |
| structlog | ≥24 | Structured logging |

## What to Avoid

- PostgreSQL — user chose SQLite; do not introduce psycopg2
- Async SQLAlchemy — use the sync engine; metadata DB calls run directly inside the async nodes (the pipeline owns a dedicated thread, so blocking is fine)
- OpenAI SDK — Gemini only
- `langchain-mcp-adapters` or any third-party MCP wrapper — official `mcp` SDK only
- The `mcp` v2 line (`main` branch) — it renames the server and removes the in-memory transport; stay on `==1.28.0`
- `alembic revision --autogenerate` before `script.py.mako` exists — it will fail

## Dependency Management

**uv** + `pyproject.toml`. All commands in docs use `uv run` prefix.

---

## Permanent Rules (apply to all projects, not filled in by tech-designer)

### Default Dev Port

All generated projects **must** use **port 8001** as the default development port (not 8000).

- `__main__.py` must hard-code `port=8001` (not 8000) unless overridden by an env var
- README must reference `http://localhost:8001`

### LLM Model Name Rule

**Always use a current, verified model name.**

- Gemini default: `gemini-2.5-flash`
- Configurable via `DATAANALYSIS_LLM_MODEL` env var

### DB Driver Rule

SQLite driver (`sqlite3`) is part of the Python standard library — no extra package needed. `aiosqlite` is NOT used (sync only).

### Test Environment Rule

Tests use SQLite (same as production). `conftest.py` creates a fresh in-memory or tmp-path database for each test session.
