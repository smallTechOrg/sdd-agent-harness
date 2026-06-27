# Tech Stack

## Language

**Python 3.12**

**Why:** User-specified. Best ecosystem for data manipulation (pandas) and AI/LLM libraries.

## Agent Framework

**LangGraph 0.2+** (async nodes)

**Why:** Structured state machine for the load → plan → execute → finalize pipeline. Makes error routing explicit. Nodes are `async def` so they can drive the async MCP client; the graph is invoked with `ainvoke()` inside a single `asyncio.run()` owned by the (already-backgrounded) pipeline thread.

## Tool Protocol

**Model Context Protocol (MCP)** via the **official `mcp` SDK, pinned `==1.28.0`**

**Why:** The primary entity is an **MCP server** (1:1 with a dataset). Per the MCP 2025-06-18 spec it has three kinds of children — **tools, resources, prompts** — which are **LLM-generated** (the sync pipeline) and **stored as rows**, served over a standards-compliant **JSON-RPC endpoint** (`POST /database/{id}`) for the UI and external MCP clients. Separately, the LangGraph agent acts as an in-process MCP **client**: the per-session pool wraps each attached server in a `FastMCP` server exposing a **generic read-only `query` tool** over its tables; the agent invokes it with `call_tool()`. The LLM↔agent ReAct protocol stays hand-rolled and uses a **single-level** call shape, `{"tool":"<server>","arguments":{"query":"SELECT …"}}`. *(Phase B also surfaces the server's generated GET-API tools to the agent — hybrid.)*

**Two surfaces, kept separate:** the agent pool (`tools/mcp/pool.py` + `server.py`, generic SQL) and the public DB-backed JSON-RPC dispatcher (`tools/mcp/dispatch.py`, reads the stored capability rows). The dispatcher does **not** use FastMCP (which cannot represent custom `inputSchema`/resources/prompts).

**Transport (agent pool):** in-process / in-memory (`mcp.shared.memory.create_connected_server_and_client_session`). No subprocess, no ports. This helper is semi-public and touches a private attribute, so it is isolated to the MCP package under **`tools/mcp/`** (`server.py` builds a server, `pool.py` is the `SessionPoolManager`, `dispatch.py` is the public JSON-RPC surface) — swapping to stdio / Streamable-HTTP / the v2 `mcp.client.Client` is then a localized change. The exact `==1.28.0` pin is deliberate: the SDK's v2 line renames the high-level server and removes the in-memory helper.

**All MCP/tool code lives under `tools/`** (ingestion, descriptions, table-naming, MCP servers, the pool manager).

**Pooling:** one MCP pool **per session** (not per query), holding one server **per attached MCP-server entity** — built lazily on first query, reused, idle/LRU-evicted, closed on session delete + shutdown (and on sync/delete of an attached server). Queries on a session are serialized by a per-session lock (the DuckDB connection is not concurrency-safe); `close()` acquires that lock before teardown so a server change never closes a connection mid-query.

**Use the official `mcp` SDK only** — do **not** add `langchain-mcp-adapters` or any third-party MCP wrapper.

## Dataset Query Engine

**DuckDB** queries each dataset, read-only.

**Why:** Each **MCP server** is backed 1:1 by a dataset addressed by a URI. The agent pool exposes a **generic read-only `query` tool** per server; the public JSON-RPC surface exposes the LLM-**generated** GET-API tools (canned, parameterized SELECTs). A dataset is either an internal **directory of Parquet files** (one CSV → one Parquet → one table) or, in BETA, an external **PostgreSQL** database. One DuckDB connection backs each server, with one **view per table**, so a query may `JOIN` the server's other tables; cross-server joins are not possible (separate servers) and are composed by the agent across ReAct iterations.

- **Internal (parquet):** DuckDB reads the dataset's Parquet files natively via `read_parquet(...)` (no load step) and ships native `STDDEV`/`VARIANCE`, so the old pandas→in-memory-SQLite copy and the custom SQLite aggregate functions are removed.
- **External (postgresql, BETA, flag-gated):** DuckDB's **postgres extension** (`postgres_scanner`) attaches the database with `ATTACH … (TYPE postgres, READ_ONLY)` and creates one view per introspected table. The `READ_ONLY` attach means the agent cannot mutate, but it can read **any** table the credentials can reach (not only the introspected ones) — scope the DB user accordingly. Gated by `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` (default off).

The **application metadata** store (PostgreSQL or SQLite, below) is separate from DuckDB, which is only
the **dataset query engine**.

## Connector Seam

**`tools/connectors/` package** — every connector **inherits from the `BaseConnector` ABC** (`base.py`).

**Why:** The query/sync path must never branch on database type. `BaseConnector` fixes the contract —
`connection_check()`, `discover_tables()`, `build_server(table_names, max_rows)` (abstract) plus
`discover_relationships()` and `drop_table(name)` (sensible defaults) — with **identical signatures and
return shapes** across all subclasses, so callers use any connector without checking its type.
`get_connector(server)` is a **registry lookup** (no type branching), with each connector module imported
lazily (avoids a base↔connector cycle; keeps drivers optional).

**Inspection (`discover_tables`/`discover_relationships`) runs ONLY in the sync pipeline**, which
materializes the tables (→ entity resources) and FK relationships (→ the schema resource) into the DB.
Everywhere else — the agent pool, `tools/call`, write-time validation, the EER view — reads the
**resources table** and calls `build_server(table_names)`, which only **builds query views over the named
tables** (parquet: views by path; postgres/sqlite: `ATTACH` + views; mongo/snowflake: load → register).
The serving path never re-inspects the store, and there is no stored `physical_tables` catalog.
`discover_relationships` returns the canonical FK-edge list (`[{from_table, from_column, to_table,
to_column}]`) — Postgres `information_schema`, SQLite `PRAGMA foreign_key_list`; the LLM backfills the
same shape when the store has none.

**Database types (one connector each):**
- **`parquet`** (internal) — `ParquetConnector`: a directory of Parquet files; inspects via pyarrow;
  serves via DuckDB views. Zero tables is valid. The only type whose tables we create/drop (file ops).
- **`postgresql`** (BETA) — `PostgresConnector`: psycopg2 connect + `information_schema`; DuckDB
  `ATTACH … (TYPE postgres, READ_ONLY)`. Exposes FK relationships is possible (currently LLM-inferred).
- **`sqlite`** — `SQLiteConnector`: stdlib `sqlite3` introspection (incl. `PRAGMA foreign_key_list` →
  `discover_relationships`); DuckDB `sqlite_scanner` (`ATTACH … (TYPE sqlite)`).
- **`mongodb`** (BETA) — `MongoDBConnector`: pymongo; collections are the tables; **loads** sampled
  documents into DuckDB-registered DataFrames for the read-only SELECT path.
- **`snowflake`** (BETA) — `SnowflakeConnector`: snowflake-connector-python; `information_schema`;
  **loads** capped table reads into DuckDB DataFrames.

External datasets are **always enabled** (no feature flag). `DatasetURI` (`uri.py`) exposes a `display()`
that **strips credentials** — every log line, stored `connection_error`, and surfaced exception uses it.
Shared SQL helpers (`_run_select`/`_run_select_params` guard + row cap, `build_server`,
`register_parquet_view`, `register_dataframe_view`, `DEFAULT_MAX_ROWS`) live in `tools/mcp/server.py`. The
SELECT guard rejects `;` stacking, `ATTACH`/`COPY`/`PRAGMA`/`INSTALL`/`LOAD`, and DuckDB file-reading
table functions — so a query reaches only the database's registered views, never arbitrary host files.

A broken database is **never persisted** — `connection_check()` runs before commit on create and sync.

**Drivers:** `psycopg2-binary` is bundled; `pymongo` and `snowflake-connector-python` are **optional**
(install to use those types — the connector raises a clear `DatasetConnectionError` if the driver is
absent). **MySQL** remains deferred.

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

**PostgreSQL** (master metadata store) via **SQLAlchemy 2.0** (sync, declarative Mapped types), with
**SQLite** fully supported as the configurable/default backend (and what the test suite uses).

**Why:** The metadata store is selected by `DATAANALYSIS_DATABASE_URL`. The deployed master DB is
PostgreSQL (`postgresql+psycopg2://…`, psycopg2 driver). The schema is backend-agnostic: partial-unique
indexes (uniqueness over active, non-soft-deleted rows) declare **both** `sqlite_where` and
`postgresql_where`; Alembic batch mode is enabled for SQLite only. This is independent of the external
**Postgres dataset** connector (BETA) — that reads a user's *data*, this stores the app's *metadata*.

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

- ~~PostgreSQL as the application metadata store~~ — **superseded:** the master metadata DB is now PostgreSQL (configurable via `DATAANALYSIS_DATABASE_URL`; SQLite still supported + used by tests). psycopg2 is used both for the app metadata engine and (separately) in `PostgresConnector` for external Postgres *datasets* (BETA + flag-gated).
- MySQL datasets — deferred (no DuckDB MySQL extension here). MongoDB + Snowflake ARE supported now
  (BETA, optional drivers); SQLite is fully supported.
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

- `DATAANALYSIS_DATASETS_DIR` — root for internal Parquet databases; physical files live at `{datasets_dir}/{slug(name)}/{table}.parquet` (keyed by the database name, which is unique). On Render this **must** point at the persistent `/data` disk, or new databases are lost on redeploy. Lifespan ensures the directory exists.
- `DATAANALYSIS_MCP_LIST_PAGE_SIZE` — page size for the JSON-RPC `*/list` cursor pagination (default 50).

External databases (postgresql/sqlite/mongodb/snowflake) are **always enabled** — there is no
feature flag; mongo/snowflake just need their optional drivers installed.

### Test Environment Rule

Tests use SQLite (same as production). `conftest.py` creates a fresh in-memory or tmp-path database for each test session.
