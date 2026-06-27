# Agent

> The DataChat agent graph. **The central design fact is the privacy boundary:** the only nodes that call Gemini send it *schema + aggregate result tables only*; the node that touches raw rows (`run_local_aggregation`) **never** calls an LLM. Raw rows are confined to `src/data/` (pandas DataFrame + the file on disk) and never enter any prompt.

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Single-agent loop** | One LLM drives a deterministic tool-call loop. |
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges. |
| Multi-agent / Supervisor / Human-in-the-loop | (not used) |

**Chosen:** **Graph (LangGraph)** — a fixed pipeline (Prompt Chaining + Tool Use from `harness/patterns/agentic-ai.md`): plan → execute-locally → compose. The graph is chosen specifically because the privacy boundary is enforced *structurally* — the local-aggregation step is a distinct node that sits between two LLM nodes and is the only one allowed to read raw rows. Memory Management (recent-turn history) supports follow-ups. Reflection on the plan is added in Phase 5.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan_aggregation` | Gemini | `gemini-2.5-pro` (env `AGENT_LLM_MODEL`) | Light reasoning: map question + compact schema → structured plan. Cheap input. |
| `compose_answer_and_pick_chart` | Gemini | `gemini-2.5-pro` | Light reasoning: small aggregate table → plain answer + chart choice. |
| `run_local_aggregation` | **none** | — | **Never calls an LLM.** Pure local pandas. This is the privacy firewall. |
| `profile_dataset` (at upload) | **none** | — | Schema inference is local; no LLM. |

**Fallback behaviour:** Phase 1 surfaces a friendly error message into the chat on LLM failure (sets `state["error"]` → `handle_error`). Phase 5 adds retry/backoff + timeout in `LLMClient` and a degraded path (return the answer without a chart if the compose call's chart selection fails). Tests call the real Gemini API with the key from `.env`.

**Prompt strategy:** System/user split. Both LLM nodes request **structured JSON output** (a fenced JSON block parsed by the node). `plan_aggregation.md` returns a plan object; `compose_answer.md` returns `{answer, chart}`. Prompts include the compact schema and (for plan) recent chat history; **neither prompt ever includes raw data rows**. Aggregate tables sent to compose are capped (≤ 50 rows) to keep tokens low.

---

## Tools & Tool Calling

The graph is a fixed pipeline, not an LLM-chooses-tools loop. The one "tool" is the local aggregation function, invoked deterministically by `run_local_aggregation` using the plan the LLM produced.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `aggregation.run_plan` | Load the stored file (pandas) and execute the aggregation plan locally | `file_path`, `AggregationPlan` | small result table (list of dict rows, capped) + actual columns used | reads local file only; no network |
| `schema.infer` | Infer column names/types + row count from a file (used at upload) | `file_path` | `Schema` (columns: name+dtype) + `row_count` | reads local file only |

**Tool selection strategy:** Rule-based — the pipeline always runs `aggregation.run_plan` with the plan from the previous node. No LLM tool-routing.

**Tool failure handling:** If `aggregation.run_plan` raises (e.g. the plan references a column that doesn't exist), the node sets `state["error"]`; the graph routes to `handle_error`. Phase 5 adds a plan-repair reflection loop instead of a hard fail.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                         # set by runner (reuses RunRow id)
    conversation_id: str                # set by runner; groups chat turns

    # Input
    dataset_id: str                     # which uploaded dataset to query
    file_path: str                      # local path to raw file (src/data/ only reads this)
    schema: dict                        # {columns: [{name, dtype}], row_count} — LLM-safe, no rows
    question: str                       # the user's plain-language question
    history: list                       # [{role, content}, ...] recent turns for follow-up context

    # Pipeline data (populated progressively)
    plan: dict | None                   # AggregationPlan from plan_aggregation (LLM)
    aggregate_table: list | None        # small result rows from run_local_aggregation (LOCAL)
    aggregate_columns: list | None      # columns present in the aggregate table

    # Output
    answer: str | None                  # plain-language answer (LLM)
    chart: dict | None                  # ChartSpec {type, title, labels, series} or None

    # Control
    error: str | None                   # set by any node on fatal failure
    status: str | None                  # "completed" | "failed"
```

> **Raw rows are NOT a field of AgentState.** They exist only transiently inside `run_local_aggregation` as a pandas DataFrame and on disk at `file_path`. Nothing downstream of that node — and no LLM prompt — ever holds raw rows. `aggregate_table` is the only data-derived payload that reaches an LLM, and it is aggregated + capped.

`AggregationPlan` shape (produced by `plan_aggregation`, consumed by `run_local_aggregation`):
```json
{ "group_by": ["region"], "metric": "sales", "agg": "sum",
  "filter": null, "sort": "desc", "limit": 50, "intent": "comparison" }
```
`agg` ∈ {sum, mean, count, min, max}; `intent` ∈ {comparison, trend, distribution, single_value} (hints the chart choice).

---

## Nodes / Steps

### `node_plan_aggregation`
**Reads from state:** `schema`, `question`, `history`
**Writes to state:** `plan`, `error?`
**LLM call:** **YES** — Gemini. Prompt = system (`plan_aggregation.md`) + compact schema + recent history + question. Output = JSON `AggregationPlan`. **Payload contains schema + history + question — NO raw rows.**
**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | plan generation | fatal (set `error`) in Phase 1; Phase 5 retries |
**Behaviour:** Translates the natural-language question (with conversation context) into a structured aggregation plan grounded in the actual schema column names.

### `node_run_local_aggregation`
**Reads from state:** `file_path`, `plan`
**Writes to state:** `aggregate_table`, `aggregate_columns`, `error?`
**LLM call:** **NO — and must never have one. This is the privacy firewall.**
**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| Local file (pandas) | load + `groupby().agg()` per plan | fatal (set `error`); Phase 5 repairs the plan |
**Behaviour:** Loads the raw file locally, executes the plan, produces a small aggregate table (≤ `plan.limit`, hard-capped at 50 rows). Raw rows never leave this node.

### `node_compose_answer_and_pick_chart`
**Reads from state:** `question`, `aggregate_table`, `aggregate_columns`, `plan.intent`
**Writes to state:** `answer`, `chart`, `error?`
**LLM call:** **YES** — Gemini. Prompt = system (`compose_answer.md`) + question + the small aggregate table + intent hint. Output = JSON `{answer, chart}`. **Payload contains only the aggregate table — NO raw rows.**
**External calls:**
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | answer + chart selection | fatal (set `error`) in Phase 1; Phase 5 degrades to answer-without-chart |
**Behaviour:** Writes a concise plain-language answer grounded in the aggregate table and picks a chart type (bar for comparison, line for trend, pie for distribution, none for single_value), emitting a `ChartSpec`. See [api.md](api.md#chart-spec) for the exact shape.

### `node_finalize`
**Reads from state:** `conversation_id`, `answer`, `chart`
**Writes to state:** `status = "completed"`
**LLM call:** NO. Persists the assistant `Message` (content + chart spec JSON) to SQLite and marks the run complete.

### `node_handle_error`
**Reads from state:** `error`, `run_id`, `conversation_id`
**Writes to state:** `status = "failed"`
**LLM call:** NO. Persists a failed run + a user-facing error message; terminates the graph.

---

## Graph / Flow Topology

```
START
  │
  ▼
plan_aggregation ──(error)──► handle_error ──► END
  │
  ▼
run_local_aggregation ──(error)──► handle_error ──► END   [LOCAL ONLY — no LLM]
  │
  ▼
compose_answer_and_pick_chart ──(error)──► handle_error ──► END
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `plan_aggregation` | `state["error"]` is set | `handle_error` |
| `plan_aggregation` | else | `run_local_aggregation` |
| `run_local_aggregation` | `state["error"]` is set | `handle_error` |
| `run_local_aggregation` | else | `compose_answer_and_pick_chart` |
| `compose_answer_and_pick_chart` | `state["error"]` is set | `handle_error` |
| `compose_answer_and_pick_chart` | else | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | plan, aggregate table, answer, chart |
| **Across runs** | SQLite (`Message` table) | full conversation turns (content + chart spec) |
| **Conversation** | recent message history passed into `plan_aggregation` | Phase 1: last N turns (default 6) for follow-ups; Phase 2: summarization of longer histories |

**Context window management:** Phase 1 passes a sliding window of the last N (default 6) turns into `plan_aggregation` only (compose doesn't need history). Phase 2 adds summarization of older turns. Aggregate tables sent to `compose` are capped at 50 rows to bound tokens.

---

## Human-in-the-Loop Checkpoints

None — fully automated per turn.

---

## Error Handling & Recovery

**Node-level:** Each node wraps its work in try/except; on a fatal error it returns `{**state, "error": str(exc)}`.

**Graph-level (`handle_error` node):**
- Reads: `state.error`, `state.run_id`, `state.conversation_id`
- Updates DB: run status → `failed`, persists a user-facing assistant message ("I couldn't answer that — …"), sets `error_message`
- Logs error with `run_id` context
- Terminates the graph

**Resume / retry strategy:** Phase 1 has no resume — a failed turn is just re-asked. Phase 5 adds LLM retry/backoff and a plan-repair reflection loop.

**Partial failure:** Phase 1 aborts the turn on any node error. Phase 5: if only the chart selection fails, degrade to returning the answer with `chart = None` rather than failing the turn.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One log line per node with `run_id` | structlog (stdout JSON) via `src/observability/events.py` |
| **LLM calls** | model, latency, which node | structured log |
| **Privacy assertion** | (test-time) the exact LLM-bound payload is inspected to confirm no raw row appears | `tests/integration/test_chat_graph.py` |
| **Run outcome** | status, error if any | SQLite (`runs`) + structured log |

---

## Concurrency Model

- **Run isolation:** one turn at a time per request; runs scoped by `run_id`/`conversation_id`. Single-user app, so no queueing needed.
- **Parallel nodes within a run:** none — the pipeline is strictly sequential (plan → aggregate → compose), which is also what enforces the privacy ordering.
- **Checkpointing:** none in Phase 1 (no human-in-the-loop, short runs).

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.nodes import (
    plan_aggregation, run_local_aggregation,
    compose_answer_and_pick_chart, finalize, handle_error,
)
from graph.edges import after_plan, after_aggregate, after_compose


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan_aggregation", plan_aggregation)
    g.add_node("run_local_aggregation", run_local_aggregation)   # NO LLM — privacy firewall
    g.add_node("compose_answer_and_pick_chart", compose_answer_and_pick_chart)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("plan_aggregation")
    g.add_conditional_edges("plan_aggregation", after_plan,
        {"run_local_aggregation": "run_local_aggregation", "handle_error": "handle_error"})
    g.add_conditional_edges("run_local_aggregation", after_aggregate,
        {"compose_answer_and_pick_chart": "compose_answer_and_pick_chart", "handle_error": "handle_error"})
    g.add_conditional_edges("compose_answer_and_pick_chart", after_compose,
        {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
```
