# Architecture

## System Overview

The data analysis agent is a single-process FastAPI application. Users interact via a browser UI (Jinja2 templates). Uploaded files are converted to **Parquet** on disk; data-source metadata, sessions, and query history live in **SQLite**. Each natural language query runs a LangGraph ReAct pipeline that acts as a **Model Context Protocol (MCP) client**: for every data source attached to the session it opens an in-process MCP **server** that wraps that source's Parquet file, discovers the server's tools (`list_tools`), and invokes them (`call_tool`) iteratively until the LLM signals a final answer.

The key architectural decision is that **a data source's capabilities are exposed through an MCP server, not hardcoded in the agent**. Uploading a CSV conceptually "creates an MCP server" that converts a tool invocation into a DuckDB query over the Parquet. Adding a new data-source type means writing a new MCP server — the agent loop, the client, and the UI shell are untouched. MCP is used **only** as the agent↔tool transport; the LLM↔agent ReAct protocol (the LLM emitting JSON tool calls) stays hand-rolled.

## Component Map

```
Browser (HTML form)
    ↓ POST /datasources/upload
FastAPI (uvicorn, sync endpoints)
    │  upload: CSV → Parquet (FileIngester) + DataSource row (+ LLM descriptions)
    │  query : create QueryRecord + AgentRun, spawn a daemon thread
    │
    └─► Pipeline thread → asyncio.run(agent_graph.ainvoke(...))
            ├── load_data      (open one in-memory MCP server+session per source; list_tools)
            ├── plan_action    (LLM picks next tool + arguments, or FINAL ANSWER)
            ├── execute_action (MCP client call_tool → DuckDB SELECT over Parquet)
            └── finalize       (persist QueryRecord; close MCP sessions)
                ↓
            SQLite (metadata, via SQLAlchemy 2.0)   +   Parquet files (queried by DuckDB)
```

## MCP Layer

```
                 graph/mcp_pool.py  (the ONLY importer of mcp.shared.memory)
                 ┌──────────────────────────────────────────────────────┐
 agent (client)  │  per run_id: AsyncExitStack + N ClientSessions        │
                 │   session_1  ◄── in-memory transport ──►  FastMCP(ds_1)│ → DuckDB → Parquet_1
                 │   session_2  ◄── in-memory transport ──►  FastMCP(ds_2)│ → DuckDB → Parquet_2
                 └──────────────────────────────────────────────────────┘
                         build_server() lives in graph/mcp/csv_server.py
```

- **Transport:** in-process / in-memory. No subprocess, no ports — `create_connected_server_and_client_session(FastMCP)` yields an already-`initialize()`d `ClientSession`.
- **One server per data source.** Each server exposes a single `run_query` tool. The pool surfaces tools to the agent under **namespaced keys** (`<table_name>__run_query`) so N connected servers never collide, and routes each `call_tool` back to the owning session.
- **Isolation seam:** every MCP import lives in `mcp_pool.py` / `mcp/csv_server.py`. The rest of the code never imports `mcp`. The `mcp` SDK is pinned `==1.28.0` (v2 removes the in-memory helper).

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (FastAPI) | HTTP routing, file upload, form handling, template rendering |
| Ingestion | CSV/XLSX/JSON → Parquet; schema + row-count extraction (`tools/ingester.py`) |
| MCP server | Per-source `FastMCP` wrapping one Parquet; `run_query` tool runs read-only DuckDB SQL (`graph/mcp/csv_server.py`) |
| MCP client pool | Open/list/call/close sessions per run; namespacing + routing (`graph/mcp_pool.py`) |
| Graph (LangGraph) | Async ReAct pipeline: load → plan → execute → loop → finalize |
| LLM (OpenRouter) | Chat completions; falls back to stub when key not set |
| Domain | Pydantic/SQLAlchemy models for all entities |
| DB (SQLAlchemy + SQLite) | Persistence of metadata, sessions, query history |
| Templates (Jinja2) | Server-rendered HTML: data sources, sessions, query history |

## Data Flow

1. **Upload:** User uploads a file → FastAPI streams it to Parquet (`FileIngester`), creates a `DataSource` record (parquet_path, schema, row_count), and stores an **LLM-generated `tool_description` and `capability_description`** on the row (so the server's tool description survives without re-calling the LLM each run).
2. **New session:** User starts a session on one or more DataSources → FastAPI creates a `Session` and `SessionDataSource` links → redirects to the session page.
3. **Query:** User asks a question → FastAPI creates a `QueryRecord` + `AgentRun` and spawns a daemon thread that calls `run_pipeline()`.
4. **Agent loop** (async, one `asyncio.run` per run on the pipeline thread):
   - `load_data`: loads the session's sources from SQLite; for each, builds a `FastMCP` server over its Parquet and opens an in-memory `ClientSession` (held in a per-`run_id` pool); aggregates `list_tools()` into `state["tools"]`.
   - `plan_action`: sends tools + schema + question + history to the LLM → receives a JSON tool call (`{"tool","arguments"}`) or `FINAL ANSWER:`.
   - `execute_action`: routes the call through the pool → `call_tool` → the server's DuckDB `SELECT` over the Parquet; appends the result (or recoverable error) to history.
   - loop back to `plan_action` until `FINAL ANSWER:` or max iterations.
   - `finalize`: persists answer, token counts, tool trace; **closes all MCP sessions** for the run.
5. **Result:** FastAPI redirects to the session page; the new answer is highlighted inline.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| OpenRouter (Gemini 2.5 Flash) | NL reasoning and action planning | Falls back to stub — answer marked as "(stub mode)" |
| `mcp` SDK (in-process) | Agent↔tool protocol | Server build / session open failure → fatal for that run (clean error) |
| DuckDB | Read-only SQL over Parquet | SQL errors are recoverable (fed back to the LLM); a missing Parquet is fatal |
| SQLite | Store metadata | App fails to start if DB file is unwritable |
| Local filesystem | Store Parquet files | Upload fails with a user-visible error |

## Concurrency & Async Model

- FastAPI endpoints stay **sync**; a query runs on a **daemon thread** (`threading.Thread`).
- `run_pipeline()` is sync and owns the event loop: `asyncio.run(agent_graph.ainvoke(...))`. All MCP work for a run therefore happens on **one task / one loop**, satisfying the MCP/AnyIO rule that an async context manager be entered and exited on the same task (LIFO). The per-`run_id` `AsyncExitStack` lives in the pool, opened in `load_data` and closed in `finalize`/`handle_error`, with a `try/finally` backstop in `run_pipeline`.
- **Constraint (non-negotiable):** do not wrap the MCP calls in `anyio.to_thread`, and do not add LangGraph parallel fan-out nodes — either moves an MCP session off its owning task and breaks the context manager.
- The sync SQLAlchemy and sync LLM `complete()` calls are invoked directly inside the async nodes; the dedicated thread makes blocking harmless.

## Deployment Model

Local single-user service. Runs with `uv run python -m data_analysis_agent` on port 8001. Single process — the MCP servers are in-memory, so there is nothing extra to deploy. No container required for v0.1.
