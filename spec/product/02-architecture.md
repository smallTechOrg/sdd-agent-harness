# Architecture

## System Overview

The data analysis agent is a single-process FastAPI application. Users interact via a browser UI (Jinja2 templates). A **tool** is a named **dataset** addressed by a URI: an internal dataset is a **directory of related Parquet files** (one uploaded CSV → one Parquet file → one **table**); an external dataset is a **database** (PostgreSQL, BETA). Dataset metadata, per-table metadata, sessions, and query history live in **SQLite**.

A **session** is the long-lived agent context. The first time a session is queried, the app builds a **per-session MCP pool** — one in-process Model Context Protocol (MCP) **server per attached dataset**, exposing **one capability per table**. Internal datasets back their tables with Parquet via DuckDB; external datasets are reached through DuckDB `ATTACH`. That pool is **reused by every subsequent query** in the session (not rebuilt per query). Each query is one LangGraph ReAct run acting as an MCP **client**: `plan_action → execute_action (call_tool) → finalize`, looping until the LLM signals a final answer. Tool calls are **two-level** — `{"tool":"<dataset>","capability":"<table>","arguments":{"query":"SELECT …"}}` — so the dataset namespaces its tables. The agent's **memory is durable per session** via a LangGraph `SqliteSaver` checkpointer keyed by `thread_id = session_id`.

Key decisions: **(1)** a dataset's capabilities are exposed through an MCP server, not hardcoded — adding a dataset *type* means writing a new connector; **(2)** MCP is only the agent↔tool transport (the LLM↔agent ReAct protocol stays hand-rolled); **(3)** all MCP/tool code lives under `tools/`, with connector implementations behind a `DatasetConnector` seam in `tools/connectors/`.

## Component Map

```
Browser (HTML form)
    ↓ POST /datasources/upload  |  POST /datasources/{id}/add-csv
    ↓ POST /sessions            |  POST /sessions/{id}/query
FastAPI (uvicorn, sync endpoints)
    │  upload : dataset_name + dataset_type + CSV → Parquet (FileIngester)
    │           → Dataset row + first DatasetTable row (+ LLM descriptions)
    │           → connection_check() BEFORE commit (broken dataset never persisted)
    │  add-csv: append a new table to an existing dataset (re-describe all tables)
    │  sync   : regenerate tool + per-table capability descriptions, connection_check()
    │  session: create SessionRow + links; best-effort warm the session pool
    │  query  : create QueryRecord + AgentRun, spawn a daemon thread
    │
    └─► Pipeline thread → SessionPoolManager.acquire(session_id)   (lazy build, reused)
                        → per-session lock → asyncio.run:
                            AsyncSqliteSaver(checkpoint_db) → build_graph().compile(checkpointer)
                            → ainvoke(input, thread_id=session_id)
            ├── plan_action    (reads grouped tools/capabilities/memory; LLM picks tool+capability, or FINAL ANSWER)
            ├── execute_action (MCP client call_tool(dataset, capability) → DuckDB SELECT)
            └── finalize       (persist QueryRecord; append turn to durable `conversation`)
                ↓
        SQLite (metadata) + checkpoint SQLite (memory) + Parquet dirs / external DB (DuckDB)
```

## MCP Layer

```
        tools/mcp/pool.py — SessionPoolManager (the ONLY importer of mcp.shared.memory)
        ┌────────────────────────────────────────────────────────────────┐
 agent  │  per session_id (held, reused across queries; LRU/idle evicted):│
        │     1 FastMCP server PER DATASET + DuckDB conns + per-session lock│
        │  per call (transient): ClientSession ─► FastMCP(dataset_i) ─► DuckDB
        │                          ├─ query_<table_a>  (view over Parquet/external)
        │                          └─ query_<table_b>  (sibling tables JOINable)
        └────────────────────────────────────────────────────────────────┘
   get_connector(dataset, tables).build_server() — tools/connectors/* + tools/mcp/server.py
```

- **Transport:** in-process / in-memory (`create_connected_server_and_client_session`). Sessions are **transient** (opened/closed within a single graph node); the servers + DuckDB connections persist for the **session** and are reused by every query.
- **One server per dataset**, one capability per table; the server registers a `query_<table>` tool per table (FastMCP requires unique tool names), each backed by a DuckDB **view**. All of a dataset's tables are views in **one** DuckDB connection, so any capability **may JOIN that dataset's other tables**; cross-dataset joins are not possible (separate servers) — the agent composes those across ReAct iterations.
- **Addressing:** the manager keys entries by `(dataset_name, table_name)` and routes `call_tool(session_id, dataset, capability, arguments)` to the owning dataset's server's `query_<capability>`.
- **Connector seam:** `tools/connectors/` provides `DatasetURI` (`uri.py`), the `DatasetConnector` Protocol + `DatasetConnectionError` + `get_connector(...)` factory (`base.py`), `ParquetConnector` (`parquet.py`), and `PostgresConnector` (`postgres.py`, BETA, flag-gated). The connector resolves the dataset URI to a DuckDB-backed server; shared SQL helpers (`build_dataset_server`, `_run_select`, `DEFAULT_MAX_ROWS`) stay in `tools/mcp/server.py`.
- **Lifecycle:** lazy build on first query; reused; **idle/LRU eviction**; closed on session delete + app shutdown; invalidated when a dataset changes (upload/add-csv/sync/delete). `close(session_id)` is **lock-safe** (acquires the per-session lock before closing) so a dataset change never closes a DuckDB conn mid-query. Queries on one session are **serialized** by a per-session lock (the DuckDB connection is not concurrency-safe).
- **Isolation seam:** every MCP import lives in `tools/mcp/`. The `mcp` SDK is pinned `==1.28.0`.

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (FastAPI) | HTTP routing, upload/add-csv/sync/delete, forms, templates; connection-check before commit; warms/closes session pools on dataset change |
| Ingestion | CSV/XLSX/JSON → Parquet; schema + row-count extraction (`tools/ingester.py`) |
| Connectors | `DatasetConnector` seam: `DatasetURI`, `get_connector` factory, `ParquetConnector`, `PostgresConnector` (BETA); `connection_check` + `discover_tables` + `build_server` (`tools/connectors/`) |
| MCP server | Per-dataset `FastMCP`, one `query_<table>` capability per table via read-only DuckDB views; `build_dataset_server`/`_run_select` (`tools/mcp/server.py`) |
| Session pool manager | Build/cache/evict per-session pools; `(dataset, table)` keying, two-level routing, lock-safe close, per-session lock (`tools/mcp/pool.py`) |
| Graph (LangGraph) | Async ReAct pipeline: plan → execute → loop → finalize (no `load_data`) |
| Memory | Durable per-session checkpointer (`SqliteSaver`, `thread_id = session_id`) |
| LLM (OpenRouter) | Chat completions; falls back to stub when key not set |
| DB (SQLAlchemy + SQLite) | Persistence of dataset + per-table metadata, sessions, query history |
| Templates (Jinja2) | Server-rendered HTML |

## Data Flow

1. **Create dataset (upload):** the form supplies a `dataset_name` + `dataset_type` (default `parquet`) + a CSV. The CSV → Parquet (`FileIngester`) at `{datasets_dir}/{dataset_id}/{table}.parquet`; create the `data_sources` (Dataset) row + the first `dataset_tables` (DatasetTable) row holding that table's parquet_path, schema, row_count, and LLM-generated `capability_description`, plus the dataset-level `tool_description`. **`connection_check()` runs before commit** — a broken dataset is never persisted.
2. **Add CSV:** `POST /datasources/{id}/add-csv` ingests another CSV as a **new table** (auto-suffixed name on collision), re-generates the dataset + per-table descriptions over **all** tables, connection-checks, and closes affected pools so the new capability becomes visible.
3. **Sync:** regenerate the dataset `tool_description` + every per-table `capability_description` from all tables; set `last_synced_at`; connection-check; close affected pools.
4. **New session:** create `Session` + `SessionDataSource` links; **best-effort warm** the session pool (`SessionPoolManager.acquire`).
5. **Query:** create `QueryRecord` + `AgentRun`; spawn a daemon thread → `run_pipeline()`.
6. **Per-query run:** acquire the session pool (lazy-build if evicted/restarted) and the per-session lock; inside one `asyncio.run`, open the checkpointer and `ainvoke` the graph with `thread_id = session_id`:
   - `plan_action`: read the **grouped** tools/capabilities snapshot from the manager + the durable `conversation`; ask the LLM for a two-level `{"tool","capability","arguments"}` call or `FINAL ANSWER:`.
   - `execute_action`: `manager.call_tool(session_id, tool, capability, arguments)` → DuckDB `SELECT` (may JOIN sibling tables in the same dataset); append result/error to the per-query `action_history`.
   - loop until `FINAL ANSWER:` or max iterations; `finalize` persists the record and appends `{question, answer}` to `conversation` (memory). **The pool is not closed here.**
7. **Result:** redirect to the session page (polls `/status`); the new answer renders inline.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| OpenRouter (Gemini 2.5 Flash) | NL reasoning / planning | Falls back to stub — "(stub mode)" |
| `mcp` SDK (in-process) | Agent↔tool protocol | Server build / session failure → fatal for that run |
| DuckDB | Read-only SQL over Parquet + external `ATTACH` | SQL errors recoverable; missing Parquet fatal |
| `langgraph-checkpoint-sqlite` | Durable per-session memory | Checkpoint DB unwritable → memory disabled / run error (degrade clearly) |
| SQLite | Metadata + checkpoint stores | App fails to start if unwritable |
| Local filesystem | Per-dataset Parquet directories (`{datasets_dir}/{dataset_id}/`) | Upload fails with a user-visible error |
| External PostgreSQL (BETA) | Live SQL datasets, gated by `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` (default off → create returns 501) | connection-check failure → sanitized `connection_error`; never persisted broken |

## Concurrency, Async & Memory Model

- FastAPI endpoints stay **sync**; a query runs on a **daemon thread**; `run_pipeline()` owns one `asyncio.run` per query.
- LangGraph runs **each node in its own task** → MCP `ClientSession`s are **transient per node**; the manager holds only plain objects (servers + DuckDB conns) across nodes and across queries.
- **Per-session serialization:** a per-session `threading.Lock` wraps each query (shared DuckDB conn). Eviction skips locked (in-use) sessions.
- **Memory:** `AsyncSqliteSaver` (file-backed) keyed by `thread_id = session_id`; a fresh saver is opened inside each query's loop (durable across these ephemeral savers and across restarts). Only `conversation` is kept in durable state; per-query scratch is reset via the `ainvoke` input.
- **Constraints (non-negotiable):** no LangGraph parallel fan-out; never span an MCP `ClientSession` across nodes; never wrap MCP calls in `anyio.to_thread`.

## Deployment Model

Local single-user service: `uv run python -m data_analysis_agent` on port 8001. Single process — MCP servers are in-memory; the metadata DB, the checkpoint DB, and Parquet files are the only on-disk state.
