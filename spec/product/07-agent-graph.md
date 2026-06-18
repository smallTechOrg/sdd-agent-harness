# Agent Graph

This graph wires the stack layers declared in [`02-architecture.md`](02-architecture.md) § Agentic
stack layers used: a context-assembly step pulls working + short-term memory
([`memory-and-context.md`](../engineering/patterns/memory-and-context.md)); `act` calls the `run_sql` /
`inspect_schema` MCP tools behind the read-only **action-safety boundary**
([`tools-and-mcp.md`](../engineering/patterns/tools-and-mcp.md)); the loop ends via the structured
`finish` tool. It follows the ReAct pattern in
[`react-agent.md`](../engineering/patterns/react-agent.md). No retrieval, long-term memory, HITL, or
checkpointer (all deferred).

## Pre-coding answers (per `react-agent.md` § Spec it before coding)

1. **Action the LLM generates:** either a tool call to `inspect_schema` (list tables/columns/types +
   sample rows) or a tool call to `run_sql` with a **read-only SQL `SELECT`** string; or the `finish`
   tool when it has the answer.
2. **`finish` tool signature:** `finish(answer: str)` — `answer` is the plain-English explanation.
   The result table to render is attached automatically from the last successful `run_sql` (carried in
   `state["result_table"]`), **not** passed back through the tool: Gemini's function-calling schema
   rejects a nested `list[list]` parameter (`items.items: missing field`), and re-sending rows the
   agent already retrieved is redundant. `node_finalize` reads `state["result_table"]`.
3. **Recoverable vs. fatal:** a bad/invalid SQL query, a read-only-guard rejection, or a DuckDB
   execution error is **recoverable** — append to `action_history`, loop back to `plan_action`. An LLM
   call failure, or the dataset's DuckDB engine being missing, is **fatal** → `handle_error`.
4. **`max_agent_iterations`:** **6.** A schema inspection + a few query refinements is ample for
   single-dataset NL→SQL; beyond that, force-finalize.
5. **`setup` prepares / cleanup:** ensures the dataset's DuckDB tables are loaded (re-materialize from
   stored files if needed) and a connection is available. The DuckDB engine is **session-scoped** (per
   dataset/conversation), kept in a module-level store — **not** released in terminal nodes; released
   only on dataset deletion (`react-agent.md` § Resource lifecycle).
6. **AgentState fields:** see below; the trace is surfaced live via `step` SSE events emitted from each
   `action_history` append (`05-api.md`).
7. **Action-safety boundary:** `run_sql` rejects anything that is not a single read-only `SELECT` — see
   § Action-safety boundary.
8. **`force_finalize`:** synthesises the best answer from `action_history` `description`/`result`
   fields (e.g. the last successful query result), noting what's incomplete — never a bare failure.

## State

```python
class AgentState(TypedDict):
    # Identity
    run_id: str
    conversation_id: str
    dataset_id: str

    # Context (assembled by node_assemble_context)
    schema_summary: str          # dataset columns + types per file
    sample_rows: str             # ≤20-row sample for grounding
    recent_turns: list[dict]     # short-term memory: prior conversation messages
    question: str                # the current user question

    # Pipeline data
    result_table: dict | None    # {"columns": [...], "rows": [[...]]} from last successful run_sql
    final_answer: str | None     # plain-English answer (set at finalize/force_finalize)

    # Control
    error: str | None            # set by any node on fatal failure

    # ReAct loop
    action_history: list[dict]   # [{"description": str, "action": str, "result": str, "is_error": bool}]
    iteration_count: int         # guarded against max_agent_iterations (6) → force_finalize
    last_tool_call: dict         # the model's last tool call — router checks if it's `finish`

    # Usage accounting (persisted on the run record)
    tokens_input: int
    tokens_output: int
    estimated_cost_usd: float | None
```

## Nodes

### `node_assemble_context`

**Reads from state:** `dataset_id`, `conversation_id`, `question`

**Writes to state:** `schema_summary`, `sample_rows`, `recent_turns`

**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | load `file` schemas/samples + recent `messages` | fatal → set `error` |
| DuckDB | ensure dataset tables are loaded (setup) | missing engine → fatal → set `error` (`DATASET_NOT_LOADED`) |

**Behaviour:** The `setup` step. Loads the dataset schema + row sample and the recent conversation
turns, and ensures the session-scoped DuckDB engine for this dataset is available (re-materializing
from stored files if needed). Builds the context once via `context.build(...)`
([`memory-and-context.md`](../engineering/patterns/memory-and-context.md)).

---

### `node_plan_action`

**Reads from state:** `schema_summary`, `sample_rows`, `recent_turns`, `question`, `action_history`

**Writes to state:** `last_tool_call`, `tokens_input`, `tokens_output`, `estimated_cost_usd`,
`iteration_count` (incremented)

**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| Google Gemini | `init_chat_model` call with the assembled context + tool schemas (`inspect_schema`, `run_sql`, `finish`) | fatal → set `error` |

**Behaviour:** Reason/plan. Asks Gemini for the next tool call given the schema, sample, prior turns,
and `action_history`. The model picks `inspect_schema`, `run_sql`, or `finish`. Returns both a
plain-English `description` and the action so the executor stores both. Accumulates token/cost usage.

---

### `node_execute_action`

**Reads from state:** `last_tool_call`, `dataset_id`

**Writes to state:** `action_history` (append), `result_table` (on a successful `run_sql`)

**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| MCP `inspect_schema` | list tables/columns/types + sample | error returned as a value → appended, recoverable |
| MCP `run_sql` (DuckDB) | **read-only** SELECT after the safety check | safety rejection or DuckDB error → value appended, recoverable |

**Behaviour:** Act + observe. Runs the chosen tool. For `run_sql`, the read-only guard validates the
query first (§ Action-safety boundary); a rejection or execution error becomes an error entry in
`action_history` (not a crash) so `plan_action` can self-correct. On a successful `run_sql`, stores the
rows in `result_table`. Emits a `step` SSE event from the appended entry's `description`.

---

## Edge Topology

```
START
  │
  ▼
node_assemble_context ──(error)──► node_handle_error ──► END
  │
  ▼
node_plan_action ──(error)──► node_handle_error ──► END
  │
  ├─(last_tool_call == finish)──────────────────────► node_finalize ──► END
  │
  ├─(iteration_count ≥ 6  OR  last N actions errored)► node_force_finalize ──► END
  │
  ▼
node_execute_action
  │
  └───────────(observe: result appended)─────────────► node_plan_action
```

Router after `node_plan_action`: if the model called `finish` → `node_finalize`; else if
`iteration_count ≥ max_agent_iterations (6)` or the last N actions all errored →
`node_force_finalize`; else → `node_execute_action`. `node_execute_action` always loops back to
`node_plan_action`.

---

## Error Handler Node (`node_handle_error`)

- Reads: `state.error`, `state.run_id`
- Updates DB: `run` status → `failed`, `error_message`, `completed_at`; persists usage fields.
- Logs error bound to `run_id`.
- Does **not** release the session-scoped DuckDB engine (the user will retry on the same dataset).
- Terminates the graph; the API surfaces it as `api_error("RUN_FAILED" | "LLM_UNAVAILABLE", …)`.

---

## Finalize Node (`node_finalize`)

- Reads: `state.run_id`, `state.last_tool_call` (the `finish` args), `state.result_table`,
  `state.action_history`, usage fields.
- Sets `final_answer` from the `finish` tool's `answer`; attaches `result_table`.
- Updates DB: `run` status → `completed`, `completed_at`; persists `action_history` + usage; writes the
  assistant `message` (content + `result_table_json` + `trace_json`).
- Logs a run summary. Does **not** release the session-scoped DuckDB engine.

---

## Force-Finalize Node (`node_force_finalize`) — ReAct loops only

- Reached when `iteration_count` hits **6** or the last N actions all errored — **not** a fatal error.
- Asks Gemini to synthesise the best answer from `action_history` (`description`/`result` fields, e.g.
  the last successful query result), noting what's missing; never emits a bare "I couldn't answer."
- Updates DB: `run` status → `completed`, records `early_exit_reason` (e.g. `"max_iterations"`);
  persists `action_history` + usage; writes the assistant `message`.
- Does **not** release the session-scoped DuckDB engine.

---

## Action-safety boundary

`run_sql` executes **model-generated SQL** — untrusted. Before any query runs against DuckDB, the
safe-executor validates it (`react-agent.md` § Action-safety boundary — use parsing, not regex):

- **Parse the SQL** (sqlglot / DuckDB's parser); reject anything that fails to parse.
- **Single statement only** — reject multi-statement input (no `;`-chained statements).
- **Read-only only** — the top-level statement must be `SELECT` (or `WITH … SELECT`). Reject any
  `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ALTER`, `ATTACH`, `COPY`, `INSTALL`, `LOAD`,
  `PRAGMA`, `EXPORT`, or `CALL`.
- **Scope to the dataset's tables** — reject references to tables outside the loaded dataset.
- Optionally enforce a row/`LIMIT` cap on results.

A rejection is returned as an **error value** appended to `action_history` (recoverable — the loop
retries with the error visible), never an exception that crashes the run. Defense-in-depth: the DuckDB
connection is opened **read-only** where possible so a slipped-through write still cannot mutate data.

## Graph Assembly (`graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("assemble_context", node_assemble_context)
graph.add_node("plan_action", node_plan_action)
graph.add_node("execute_action", node_execute_action)
graph.add_node("finalize", node_finalize)
graph.add_node("force_finalize", node_force_finalize)
graph.add_node("handle_error", node_handle_error)

graph.set_entry_point("assemble_context")

graph.add_conditional_edges(
    "assemble_context",
    lambda s: "handle_error" if s.get("error") else "plan_action",
)

def route_after_plan(s):
    if s.get("error"):
        return "handle_error"
    if s["last_tool_call"].get("name") == "finish":
        return "finalize"
    if s["iteration_count"] >= 6 or _last_n_errored(s):
        return "force_finalize"
    return "execute_action"

graph.add_conditional_edges("plan_action", route_after_plan)
graph.add_edge("execute_action", "plan_action")  # observe → loop
graph.add_edge("finalize", END)
graph.add_edge("force_finalize", END)
graph.add_edge("handle_error", END)

compiled_graph = graph.compile()  # no checkpointer in v1 (durability deferred)
```

## Concurrency Model

- **One run at a time per conversation** — enforced at the API layer (a new question on a conversation
  with an active run returns 409). Different conversations/datasets run independently.
- **Checkpointing:** none in v1 — runs are short single question→answer cycles; durability is deferred
  ([`02-architecture.md`](02-architecture.md)).
- The session-scoped DuckDB engine is shared across runs in the same conversation (short-term memory),
  released only on dataset deletion.
