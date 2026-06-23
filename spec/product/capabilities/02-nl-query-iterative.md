# Capability 2: Natural Language Query (Iterative MCP Tool-Call ReAct Loop)

## Overview

The agent answers a user's natural language question by acting as an **MCP client**: it discovers the tools exposed by each attached data source's MCP server and invokes them iteratively until it has enough information to give a confident final answer.

This is a **ReAct loop**: the LLM reasons, selects an MCP tool to call, observes the result, and repeats until it emits `FINAL ANSWER:`. Tools are not hardcoded — they are discovered at runtime via `list_tools()`, making the loop reusable across any data-source type that ships an MCP server.

## User-Facing Behaviour

1. User types a natural language question in a session.
2. The agent opens one in-memory MCP server+session per attached data source and lists their tools.
3. The agent runs one or more MCP tool calls (each a read-only DuckDB `SELECT` over a Parquet file).
4. When the LLM determines it has enough information, it returns a plain-text final answer.
5. The session page shows the answer inline with: iteration count, token usage, cost estimate, and a collapsible tool-call trace.

## Agent Loop (ReAct)

```
load_data (load DataSource rows + open one MCP server+session per source; list_tools)
    │
    ▼
plan_action ◄─────────────────────────────────────────┐
    │                                                  │
    ├── (FINAL ANSWER:) → finalize → END               │
    │                                                  │
    └── (tool call JSON) → execute_action ─────────────┘
                               │  (MCP client call_tool → DuckDB SELECT)
                               └── (isError) → plan_action (self-correction)
                               └── (max iterations) → handle_error
```

## LLM Protocol

### Tool call format (LLM output when it wants to act)

```json
{"tool": "ds_2024_sales__run_query", "arguments": {"query": "SELECT ..."}}
```

The `tool` value is the exact namespaced tool name advertised in the prompt (`<table_name>__run_query`).

### Termination format (LLM output when it's done)

```
FINAL ANSWER: <the complete answer in plain text>
```

## Termination Conditions

| Condition | Action |
|-----------|--------|
| LLM emits `FINAL ANSWER: ...` | Extract answer, route to `finalize` |
| DuckDB SQL error / non-SELECT SQL | MCP tool returns `isError=True`; append to history, loop back to `plan_action` |
| Unknown tool name | Recoverable; pool returns a valid-tool-list message, loop back |
| Malformed (non-JSON) LLM tool call | Recoverable; ask the LLM to reformat, loop back |
| Iteration count ≥ `max_agent_iterations` (default 10) | Route to `handle_error` |
| LLM call fails / missing Parquet / MCP session failure | Fatal — route to `handle_error` |

## Tool Execution Rules (`run_query` via DuckDB)

- Only `SELECT` statements are allowed. A non-SELECT statement is returned as a recoverable `isError=True` result (never executed).
- DuckDB queries the Parquet file directly through a read-only view named `<table_name>` (the same name advertised to the LLM).
- Results are capped at 200 rows (`DATAANALYSIS_MCP_MAX_RESULT_ROWS`) and returned as compact CSV.
- DuckDB provides native `STDDEV`/`VARIANCE`/`MEDIAN`/`QUANTILE` — no custom aggregates needed.

## Prompt Protocol

### `plan_action` prompt (each iteration)

```
You are a data-analysis agent operating in a ReAct loop.

Available tools (call a tool by its exact name):

Tool: ds_2024_sales__run_query  (queries table: ds_2024_sales)
  Description: <capability_description>
  Parameters: {"query": {"type": "string", "description": "A valid SQL SELECT statement."}}

SQL dialect: DuckDB. Only SELECT statements are permitted.

Dataset schema:
  Table: ds_2024_sales — Columns: <columns>

User question: <question>

<if history:>
Previous tool calls and results:
[1] tool: ds_2024_sales__run_query
    arguments: {"query": "SELECT ..."}
    result: ...
</end if>

Decide your next step. Respond with EXACTLY ONE of:
1. {"tool": "<name>", "arguments": {"query": "SELECT ..."}}
2. FINAL ANSWER: <your complete answer here>
```

## State Fields

| Field | Type | Description |
|-------|------|-------------|
| `tools` | `list[dict]` | From `list_tools()`: `[{"name", "table_name", "description", "parameter_schema"}]` (flat) |
| `action_history` | `list[dict]` | Each entry: `{"tool": str, "arguments": dict, "result": str, "is_error": bool}` |
| `iteration_count` | `int` | Number of tool calls executed so far |
| `llm_response` | `str` | Raw LLM output from last `plan_action` call |

(The MCP `ClientSession`s themselves live in the per-`run_id` pool, not in state.)

## Persistence

| Field | Stored in DB |
|-------|-------------|
| `answer` | Yes (`query_records.answer`) |
| `iteration_count` | Yes (`query_records.iteration_count`) |
| `action_history` | Yes (`query_records.query_history_json`) — displayed as the agent reasoning trace |
| Token counts, cost | Yes (existing columns on `query_records`) |

## Out of Scope (this capability)

- Streaming intermediate results to the browser (deferred)
- Chart generation from tool results (Capability 5)
- Cross-source SQL joins in a single query (each MCP server wraps one Parquet; combine across tool calls)
- Non-CSV data source types (future MCP servers)
