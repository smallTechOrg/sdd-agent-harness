# Agent

---

## Agent Architecture Pattern

**Chosen:** **Graph (LangGraph)** — the analysis is a multi-step reasoning loop (generate SQL → execute locally → inspect → answer) with a conditional **retry-on-SQL-error** edge. A graph models the conditional retry and the local-execute step cleanly; a plain loop would not capture the error-feedback edge as first-class. The skeleton already ships a 3-node LangGraph (`transform_text → finalize | handle_error`); this spec replaces the capability node in place and adds the SQL nodes.

> **Privacy boundary is enforced at the node level.** Only `execute_sql` touches raw data, and it runs entirely inside DuckDB on the local machine. The nodes that call Gemini (`generate_sql`, `answer`) are passed **only** schema, the question, prior SQL/error text, and small aggregate **result rows** — never raw source rows. The graph contains no node that forwards a raw-row sample to the LLM.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `generate_sql` | Gemini | `gemini-3.1-pro` | Needs strong SQL reasoning over schema; quality over latency. |
| `answer` | Gemini | `gemini-3.1-pro` | Phrases a careful analyst answer from aggregates; same model keeps it simple. |

Model is env-configurable (`AGENT_LLM_MODEL`); default `gemini-3.1-pro`. Provider auto-detected from `AGENT_GEMINI_API_KEY`.

**Fallback behaviour:** On transient Gemini errors (timeout / 429 / 5xx), retry with backoff (bounded). On persistent failure the run is marked `failed` with a surfaced error message — the agent **never** fabricates a number. This is production resilience, not a test stub: tests call the real Gemini API via `.env`.

**Prompt strategy:** System prompt (`src/prompts/analysis.md`) pins the DuckDB dialect and the privacy rules; user message carries the question + schema (and, in `answer`, the result rows). `generate_sql` requests SQL only (parsed/validated); `answer` requests prose. Few-shot DuckDB date examples are included in the system prompt to prevent SQLite idioms.

---

## Tools & Tool Calling

This graph uses **direct node functions**, not LLM-chosen tools. The "tool" the model influences is DuckDB execution, invoked deterministically by `execute_sql` using the SQL the model produced.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `duckdb_execute` | Run generated SQL against the dataset's local DuckDB file | `sql: str`, `dataset_path: str` | result rows (list[dict], capped) or DuckDB error | none (read-only query) |

**Tool selection strategy:** Forced/deterministic — `execute_sql` always runs the SQL from `generate_sql`. No LLM tool-routing.

**Tool failure handling:** A DuckDB error does not abort; it routes back to `generate_sql` with the error text (retry-on-SQL-error), up to `max_sql_retries`. Exhausting retries sets `error` and routes to `handle_error`.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                      # set by runner before invoke
    dataset_id: str                  # which dataset to query
    dataset_path: str                # local DuckDB file path (set by runner)
    schema: list[dict]               # [{name, type}, ...] — set by runner from Dataset; sent to LLM
    question: str                    # the user's plain-English question (input)

    # Pipeline data (populated by nodes)
    sql: str | None                  # DuckDB SQL from generate_sql
    sql_error: str | None            # last DuckDB error (fed back on retry); cleared on success
    sql_attempts: int                # retry counter (starts 0)
    result_rows: list[dict] | None   # aggregate result from execute_sql (capped); LLM-visible

    # Output
    answer_text: str | None          # plain-English answer from answer node
    output_text: str | None          # serialized answer+SQL+result for the Run row / API

    # Control
    status: str                      # "completed" | "failed"
    error: str | None                # fatal error → handle_error
```

`max_sql_retries` (default 3) is a runner constant, not state.

---

## Nodes / Steps

### `generate_sql`
- **Reads from state:** `question`, `schema`, `sql` (prior), `sql_error` (prior), `sql_attempts`
- **Writes to state:** `sql`, increments `sql_attempts`
- **LLM call:** yes — `gemini-3.1-pro`. Prompt = `analysis.md` system (DuckDB dialect pinned) + question + schema + (if retrying) prior SQL and verbatim DuckDB error. Output: SQL string only.
- **External calls:** Gemini → on transient failure, retry/backoff; on persistent failure set `error`.
- **Behaviour:** Produces a DuckDB query that answers the question against the schema. On a retry it must correct the previous query using the fed-back error. Receives schema only — no raw rows.

### `execute_sql`
- **Reads from state:** `sql`, `dataset_path`
- **Writes to state:** `result_rows` (on success, clears `sql_error`) OR `sql_error` (on DuckDB error)
- **LLM call:** no.
- **External calls:** DuckDB (local, read-only). On error → set `sql_error` (not fatal; routes to retry).
- **Behaviour:** Runs the SQL locally in DuckDB, captures the result (capped, e.g. ≤1000 rows). Raw data stays on the machine; only the (aggregate) result is carried forward. A DuckDB error message is captured verbatim for feedback.

### `answer`
- **Reads from state:** `question`, `schema`, `sql`, `result_rows`
- **Writes to state:** `answer_text`, `output_text`
- **LLM call:** yes — `gemini-3.1-pro`. Prompt = question + schema + result rows (aggregates). Output: plain-English analyst answer; if the result is ambiguous the model is instructed to flag a best-guess rather than invent precision.
- **External calls:** Gemini.
- **Behaviour:** Phrases the answer from the result, attaches the exact SQL. Receives only aggregate result rows — never raw source rows.

### `finalize`
- **Reads:** `answer_text`, `sql`, `result_rows` · **Writes:** `status="completed"`, `output_text`. No LLM. Persists handled by the runner.

### `handle_error`
- **Reads:** `error` · **Writes:** `status="failed"`. No LLM. The Run row is marked `failed` with the error message; the user sees a flagged failure, never a fabricated number.

---

## Graph / Flow Topology

```
START
  │
  ▼
generate_sql ──(error)──► handle_error ──► END
  │
  ▼
execute_sql ──(sql_error & attempts<max)──► generate_sql   (retry-on-SQL-error)
  │                                          
  ├──(sql_error & attempts>=max)──► handle_error ──► END
  │
  ▼ (success)
answer ──(error)──► handle_error ──► END
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `generate_sql` | `state["error"]` set | `handle_error` |
| `generate_sql` | otherwise | `execute_sql` |
| `execute_sql` | `sql_error` set AND `sql_attempts < max_sql_retries` | `generate_sql` (retry) |
| `execute_sql` | `sql_error` set AND `sql_attempts >= max_sql_retries` | `handle_error` |
| `execute_sql` | no `sql_error` | `answer` |
| `answer` | `state["error"]` set | `handle_error` |
| `answer` | otherwise | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | question, schema, SQL, error, result |
| **Across runs** | SQLite (`runs` table) | audit trail: question, SQL, result, tokens, timestamp |
| **Conversation** | SQLite (`sessions` + conversation turns) — **Phase 3** | prior Q/A turns fed into `generate_sql` for follow-up context |

**Context window management:** Only schema + capped result rows enter prompts, so context stays small. In Phase 3, conversation history is summarised/windowed before being added to the planning prompt.

> **Phase 1 scope:** the live graph is `generate_sql → execute_sql → answer → finalize`, with the retry-on-SQL-error edge. Profiling, chart-spec, summary-table, follow-up, planning, and validation nodes (the fuller analyst loop) are the **target for Phases 2–3** and are documented in the capability files; they are not in the Phase 1 graph.

---

## Human-in-the-Loop Checkpoints

None in Phase 1 (single-shot ask). Ambiguity handling: in Phase 2+, on genuinely ambiguous questions the `answer` node may return a clarifying question instead of a flagged guess; Phase 1 returns a clearly-flagged best-guess answer.

---

## Error Handling & Recovery

**Node-level:** each node catches its own exceptions; a fatal LLM/infra error sets `state["error"]` and routes to `handle_error`. A DuckDB *query* error is **not** fatal — it sets `sql_error` and routes to the retry edge.

**Graph-level (`handle_error`):** reads `error`/`run_id`, marks the Run `failed` with `error_message`, logs with `run_id` context, terminates.

**Resume / retry strategy:** the SQL retry loop is in-graph (bounded by `max_sql_retries`). Failed runs are not auto-resumed; the user re-asks.

**Partial failure:** if the answer phrasing fails but a result exists, the run is marked failed rather than returning an unverified number — correctness over partial output.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One log context per run, one event per node | structlog → stdout (Phase 1, from day one) |
| **LLM calls** | Prompt tokens, completion tokens, latency, model, node | structured log + persisted on Run (`tokens`) |
| **SQL** | generated SQL, attempt number, DuckDB error on retry | structured log + Run row |
| **Run outcome** | status, total duration, error | SQLite `runs` + structured log |

LangSmith may be enabled via `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` if the user sets them; structured stdout logging is the always-on baseline and ships in Phase 1.

---

## Concurrency Model

- **Run isolation:** single-user, one analysis at a time per request; runs are `run_id`-scoped. No 409 needed for the local single user.
- **Parallel nodes within a run:** none — the path is sequential with a retry edge.
- **Checkpointing:** none in Phase 1 (no human-in-the-loop, short runs). Conversation persistence in Phase 3 is via SQLite, not a LangGraph checkpointer.

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("generate_sql", generate_sql)
graph.add_node("execute_sql", execute_sql)
graph.add_node("answer", answer)
graph.add_node("finalize", finalize)
graph.add_node("handle_error", handle_error)

graph.set_entry_point("generate_sql")

graph.add_conditional_edges(
    "generate_sql",
    lambda s: "handle_error" if s.get("error") else "execute_sql",
    {"handle_error": "handle_error", "execute_sql": "execute_sql"},
)
graph.add_conditional_edges(
    "execute_sql",
    after_execute,   # sql_error + attempts<max → generate_sql; sql_error + attempts>=max → handle_error; else → answer
    {"generate_sql": "generate_sql", "handle_error": "handle_error", "answer": "answer"},
)
graph.add_conditional_edges(
    "answer",
    lambda s: "handle_error" if s.get("error") else "finalize",
    {"handle_error": "handle_error", "finalize": "finalize"},
)
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
