# Agent Graph

> **Mandatory pre-coding checklist** — answer all before writing node code. (See `ai-agents.md` §10.)
>
> 1. **Action type:** A single-level MCP tool call naming an MCP server. Free SQL: `{"tool": "<server>",
>    "arguments": {"query": "<SQL>"}}` (generic read-only SELECT over that server's tables). Phase B adds an
>    optional `capability` to call a generated GET-API tool: `{"tool": "<server>", "capability":
>    "<gen tool>", "arguments": {<params>}}`. Absent `capability` ⇒ free SQL.
> 2. **Termination signal:** Response starts with `FINAL ANSWER:`.
> 3. **Recoverable vs fatal:** DuckDB SQL errors and non-SELECT SQL → recoverable (the MCP tool returns
>    `isError=True`, fed back). Unknown server name → recoverable. LLM-call failure, missing Parquet,
>    MCP server/session failure → fatal.
> 4. **Max iterations default:** `10` (`DATAANALYSIS_MAX_AGENT_ITERATIONS`).
> 5. **In-session resource:** a **per-session** pool (`tools/mcp/pool.py`, `SessionPoolManager`) holds one
>    built FastMCP server (+ DuckDB connection) per attached MCP-server entity for the session's lifetime;
>    built lazily on the first query, reused after. `ClientSession`s are **transient** (one node).
> 6. **Memory:** durable per-session memory via a LangGraph **`SqliteSaver`** checkpointer
>    (`thread_id = session_id`). The checkpointed state carries a growing `conversation`; per-query scratch
>    is reset via the `ainvoke` input.
> 7. **Tools the agent has:** one FastMCP server **per attached MCP-server entity**, exposing a **generic
>    `query` tool** that runs a read-only SELECT over all of that server's tables (registered as views in
>    one DuckDB connection — within-server JOINs work). `plan_action` reads them from the manager.
>    *(Phase B also surfaces the server's generated GET-API tools here — hybrid: prefer a matching
>    generated tool, fall back to the generic SQL tool.)*
> 8. **Exact tool invocation format:** the single-level JSON above — `{"tool": "<server>", "arguments":
>    {"query": "<SQL>"}}`.
> 9. **What triggers tool registration:** `POST /database` creates the `Database` row (+ generated
>    capability rows via sync); the agent's in-process server is built when the **session** pool is first
>    acquired, with one DuckDB view per physical table.

---

## State

Split into **durable memory** (restored by the checkpointer) and **per-query scratch** (reset each query
via the `ainvoke` input). Tools/schema are **not** in state — read from the `SessionPoolManager`.

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    query_record_id: str
    session_id: str          # also the checkpointer thread_id

    # Input (scratch — supplied fresh each query)
    question: str

    # Durable memory — PLAIN last-value channel (NOT a reducer). finalize writes the FULL list.
    conversation: list[dict]   # [{"question": str, "answer": str}]

    # Per-query scratch (reset via the ainvoke input each query)
    action_history: list[dict]   # [{"tool", "arguments", "result", "is_error", "capability"?}]  capability only on generated-tool calls
    iteration_count: int
    llm_response: str
    answer: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    api_request_count: int

    # Control
    error: str | None
```

> **`conversation` is a plain last-value channel, not a reducer.** `finalize` returns the FULL conversation
> list (old turns + the new turn). An `operator.add` reducer would **double-append** when the checkpoint is
> restored at the start of the next query — do not reintroduce one. The MCP servers + DuckDB connections
> (not serialisable) live in the `SessionPoolManager` keyed by `session_id`, never in state.

---

## Async lifecycle (read before touching nodes)

LangGraph runs **each node in its own asyncio task**. AnyIO ties an async CM's cancel scope to the task
that entered it, so a `ClientSession` **cannot be opened in one node and closed in another**. Therefore:

- All nodes are `async def`. `run_pipeline()` (sync, on the request's daemon thread) acquires the session
  lock, then drives `asyncio.run(ainvoke(...))`.
- The **`SessionPoolManager`** holds only **plain, task-safe objects** across nodes and queries: one built
  FastMCP server (+ DuckDB connection) per attached MCP-server entity. It never holds open `ClientSession`s.
- Each MCP operation opens a **transient** in-memory `ClientSession` within one node: `plan_action` reads
  cached descriptors from the manager (no session); `execute_action` opens a session to `call_tool()`.
- **Pool teardown is NOT in the query path.** `finalize`/`handle_error` do not close the pool — the manager
  closes it on session delete, app shutdown, and idle/LRU eviction.
- **Per-session serialization:** a per-session `threading.Lock` wraps each query (the DuckDB connection is
  not concurrency-safe); eviction skips locked sessions.
- **Do not** add parallel fan-out, span a `ClientSession` across nodes, or make `conversation` a reducer.

---

## Nodes

The per-query loop is **`plan_action → execute_action → finalize / handle_error`** — no `load_data` node
(servers + tables load once when the session pool is built).

### `plan_action` (entry point)

Reads the session's servers snapshot from the `SessionPoolManager` (by `session_id`) — one entry per
attached server, each with its description, tables, and columns. Builds a prompt with the available
servers, the durable `conversation`, the question, and the current-query `action_history`. Sends to the
LLM; accumulates tokens. `FINAL ANSWER:` → set `answer`, route to `finalize`; else store `llm_response`,
route to `execute_action`. Stub tag: `<node:plan_action>`.

### `execute_action`

Parse `{"tool","arguments"}` (bad JSON or missing `tool` → recoverable, loop back). Route through the
manager: `manager.call_tool(session_id, tool, arguments)` resolves the server, opens a transient session →
`call_tool` → `CallToolResult.content[0].text` + `.isError`. Append the observation
`{"tool","arguments","result","is_error"}`, increment `iteration_count`; at the cap, set `error`.

### `finalize`

Update the QueryRecord (answer, iteration_count, `query_history_json`, tokens, status=completed) and the
AgentRun (completed). **Returns the full `conversation` list** (old + the new `{"question","answer"}`
turn). **Does not close the pool.**

### `handle_error`

Mark QueryRecord/AgentRun `failed` (best-effort). **Does not close the pool.** Terminates the graph.

---

## Edge Topology

```
START → plan_action ◄───────────────────────────┐
          ├──(error)──► handle_error ──► END      │
          ├──(FINAL ANSWER)──► finalize ──► END   │
          └──(tool call)──► execute_action ───────┘
                               ├──(fatal)──► handle_error
                               └──(iter >= max)──► handle_error
```

## Graph Assembly

`build_graph()` returns an **uncompiled** `StateGraph`; `run_pipeline` compiles it per query with the
session's checkpointer so memory binds to `thread_id = session_id`.

```python
# per query, inside the run's event loop:
async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db) as saver:
    graph = build_graph().compile(checkpointer=saver)
    final = await graph.ainvoke(_fresh_input(state), config={"configurable": {"thread_id": session_id}})
```

`_fresh_input` supplies the new `question` and resets all scratch (`action_history=[]`,
`iteration_count=0`, `llm_response=""`, `answer=""`, usage=0, `error=None`); it **omits `conversation`** so
the restored history is preserved (and `finalize` overwrites it with the full list). Routing stays sync.

---

## Tool Prompt Format

```
Conversation so far:
[1] Q: What were total sales? → A: 60.
...

Available tools (each tool is an MCP server backed by a dataset; pick one and write SQL):

Tool: sales  (server)
  Description: 2024 sales records and the regional lookup that supports them.
  Tables (all queryable in one connection — you may JOIN them):
    orders(order_id BIGINT, region_id BIGINT, amount DOUBLE, order_date DATE)
    regions(region_id BIGINT, region_name VARCHAR)

SQL dialect: DuckDB. Only SELECT statements are permitted.

To use a tool: {"tool": "sales", "arguments": {"query": "SELECT ..."}}
To finish:     FINAL ANSWER: <your complete answer here>
```

*(Phase B: when a server also advertises generated GET-API tools, the prompt lists them with their
parameters; the agent may call one by name instead of writing SQL, and the generic `query` tool remains
as the fallback.)*

---

## Concurrency & Memory Model

- One query at a time **per session** (per-session `threading.Lock`; the DuckDB connection is not
  concurrency-safe). Different sessions run independently.
- Each query owns one event loop (`asyncio.run`); the session pool (servers + DuckDB conns) persists across
  queries in the `SessionPoolManager`.
- **Memory:** durable via `AsyncSqliteSaver` keyed by `thread_id = session_id`; `conversation` accumulates
  (plain channel; `finalize` writes the full list) and survives restarts.
- **Pool lifecycle:** lazy build; idle/LRU eviction (`max_session_pools`, `session_pool_idle_seconds`);
  closed on session delete and app shutdown; invalidated when a session's servers change.
```
