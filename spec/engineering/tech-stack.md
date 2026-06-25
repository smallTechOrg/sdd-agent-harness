# Tech Stack

## Language

**Python 3.12**

**Why:** User-specified. Best ecosystem for data manipulation (pandas) and AI/LLM libraries.

## Agent Framework

**LangGraph 0.2+** (async nodes)

**Why:** Structured state machine for the load → plan → execute → finalize pipeline. Makes error routing explicit. Nodes are `async def` so they can drive the async MCP client; the graph is invoked with `ainvoke()` inside a single `asyncio.run()` owned by the (already-backgrounded) pipeline thread.

## Tool Protocol

**Model Context Protocol (MCP)** via the **official `mcp` SDK, pinned `==1.28.0`**

**Why:** The agent's tools are formalized as MCP. Each **dataset** is wrapped by an in-process `FastMCP` server exposing one tool per table (`query_{table}`); the agent is an MCP **client** that discovers tools with `list_tools()` and invokes them with `call_tool()`. The LLM↔agent ReAct protocol stays hand-rolled and uses a two-level call shape, `{"tool":"<dataset>","capability":"<table>","arguments":{"query":"SELECT …"}}` — MCP is only the agent↔tool transport.

**Transport:** in-process / in-memory (`mcp.shared.memory.create_connected_server_and_client_session`). No subprocess, no ports. This helper is semi-public and touches a private attribute, so it is isolated to the MCP package under **`tools/mcp/`** (`server.py` builds a server, `pool.py` is the `SessionPoolManager`) — swapping to stdio / Streamable-HTTP / the v2 `mcp.client.Client` is then a localized change. The exact `==1.28.0` pin is deliberate: the SDK's v2 line renames the high-level server and removes the in-memory helper.

**All MCP/tool code lives under `tools/`** (ingestion, descriptions, table-naming, MCP servers, the pool manager).

**Pooling:** one MCP pool **per session** (not per query), holding one server **per attached dataset** — built lazily on first query, reused, idle/LRU-evicted, closed on session delete + shutdown (and on add-csv/sync/delete of an attached dataset). Queries on a session are serialized by a per-session lock (the DuckDB connection is not concurrency-safe); `close()` acquires that lock before teardown so a dataset change never closes a connection mid-query.

**Use the official `mcp` SDK only** — do **not** add `langchain-mcp-adapters` or any third-party MCP wrapper.

## Dataset Query Engine

**DuckDB** queries each dataset, read-only.

**Why:** A "tool" is now a **named dataset** addressed by a URI, and each dataset is wrapped by one MCP server exposing **one capability per table**. A dataset is either an internal **directory of Parquet files** (one CSV → one Parquet → one table) or, in BETA, an external **PostgreSQL** database. One DuckDB connection backs each dataset, with one **view per table**, so any capability may `JOIN` the other tables in the **same** dataset; cross-dataset joins are not possible (separate servers) and are composed by the agent across ReAct iterations.

- **Internal (parquet):** DuckDB reads the dataset's Parquet files natively via `read_parquet(...)` (no load step) and ships native `STDDEV`/`VARIANCE`, so the old pandas→in-memory-SQLite copy and the custom SQLite aggregate functions are removed.
- **External (postgresql, BETA, flag-gated):** DuckDB's **postgres extension** (`postgres_scanner`) attaches the database with `ATTACH … (TYPE postgres, READ_ONLY)` and creates one view per introspected table. The `READ_ONLY` attach means the agent cannot mutate, but it can read **any** table the credentials can reach (not only the introspected ones) — scope the DB user accordingly. Gated by `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` (default off).

SQLite remains the **application metadata** store (below); DuckDB is only the **dataset query engine**.

## Connector Seam

**`tools/connectors/` package** abstracts dataset access behind a `DatasetConnector` Protocol.

**Why:** The query path must not branch on dataset type inline. A connector exposes `connection_check()`, `discover_tables()`, and `build_server(max_rows)`; `get_connector(dataset_row, table_rows)` dispatches on `type`. `ParquetConnector` is fully implemented; `PostgresConnector` (BETA, flag-gated) is the only place psycopg2 is used. `DatasetURI` (in `uri.py`, built on `urllib.parse`) parses the URI and exposes a `display()` that **strips credentials** — every log line, stored `connection_error`, template field, and surfaced exception uses `display()` only. Shared SQL helpers (`_run_select` SELECT-only guard + row cap, `build_dataset_server`, `DEFAULT_MAX_ROWS`) stay in `tools/mcp/server.py`.

**External connection-check / introspection:** **`psycopg2`** performs the real `connect` + `SELECT 1` + `information_schema` introspection for external datasets (with a hard timeout). This is independent of DuckDB's attach-based query path. Internal datasets are checked by confirming the directory and each Parquet file are readable. A broken dataset is **never persisted** — the check runs before commit on create, add-csv, and sync.

**Deferred database types:** **MySQL** (DuckDB extension not installed here) and **DocumentDB/Mongo** (non-SQL — does not fit the table/`SELECT` model, so not a drop-in) are explicitly deferred and are **not** trivial additions.

## Agent Memory

**Durable per-session memory** via LangGraph's **`SqliteSaver` checkpointer** (`langgraph-checkpoint-sqlite`), keyed by `thread_id = session_id`.

**Why:** Sessions are long-lived agent contexts; prior Q&A turns feed into later questions. The checkpoint lives in its own SQLite file (separate from the Alembic-managed metadata DB) and survives restarts. Only the accumulating `conversation` is kept in the durable state; per-query scratch is reset each query. Because each query runs in its own `asyncio.run`, the **async** saver (`AsyncSqliteSaver`) is opened inside the run and the graph is compiled with it per query (the file-backed store makes this durable across the ephemeral savers).

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
| duckdb | ≥1.1,<2 | Read-only SQL over each dataset; `postgres_scanner` extension for external `ATTACH … READ_ONLY` (BETA) |
| psycopg2-binary | ≥2.9 | External Postgres connection-check + `information_schema` introspection (BETA, only used by `PostgresConnector`) |
| langgraph-checkpoint-sqlite | latest | Durable per-session agent memory (`SqliteSaver`/`AsyncSqliteSaver`) |
| google-genai | ≥1.0 | Gemini SDK |
| pandas | ≥2.2 | CSV→Parquet ingestion + schema extraction |
| pyarrow | ≥14 | Parquet engine for pandas |
| structlog | ≥24 | Structured logging |

## What to Avoid

- PostgreSQL as the **application metadata** store — user chose SQLite; the metadata DB stays SQLite. (psycopg2 IS used, but **only** in `PostgresConnector` to query external Postgres *datasets*, BETA + flag-gated — not for app metadata.)
- MySQL / DocumentDB (Mongo) datasets — deferred; do not add MySQL or Mongo drivers
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

### Dataset Settings

Two settings drive the dataset layer (via `pydantic-settings`, `DATAANALYSIS_` prefix):

- `DATAANALYSIS_DATASETS_DIR` — root for internal Parquet datasets; physical files live at `{datasets_dir}/{dataset_id}/{table}.parquet` (keyed by dataset_id so renames never move files). On Render this **must** point at the persistent `/data` disk, or new datasets are lost on redeploy. Lifespan ensures the directory exists.
- `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` — default **off**; when off, the external-dataset create path returns HTTP 501 and the UI hides the external option. External Postgres is BETA.

### Test Environment Rule

Tests use SQLite (same as production). `conftest.py` creates a fresh in-memory or tmp-path database for each test session.
