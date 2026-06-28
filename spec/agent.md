# Agent

---

## Agent Architecture Pattern

**Chosen: Graph (LangGraph).** A bounded plan → generate-code → execute → inspect → refine loop with a conditional clarify-first branch and a step limit. This is a multi-step pipeline with conditional edges and a refinement cycle — exactly what LangGraph is for; a linear loop can't express the inspect→refine-or-finish branch cleanly.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan` | Gemini | `gemini-2.5-flash` | Cheap/fast strategy planning over schema only. |
| `generate_code` | Gemini | `gemini-2.5-flash` | Pandas code generation; flash is sufficient and cost-favoured. |
| `inspect` | Gemini | `gemini-2.5-flash` | Reads code output/aggregates, decides refine-or-finish. |
| `clarify` | Gemini | `gemini-2.5-flash` | Detects ambiguity, drafts the clarifying question. |
| `finalize` | Gemini | `gemini-2.5-flash` | Composes prose + picks chart spec. |

Model is env-configurable via `AGENT_GEMINI_MODEL` (default `gemini-2.5-flash`).

**Fallback behaviour:** each LLM call retries twice with exponential backoff on transient errors (429/5xx). On persistent failure the node sets `state["error"]`, the graph routes to `handle_error`, the run is marked `failed`, and the partial steps are kept in history. This is production resilience, not a test stub — tests call the real Gemini API with the key from `.env`.

**Prompt strategy:** system/user split per node, prompts in `src/prompts/*.md`. `generate_code` uses structured output (a JSON object `{code: str, intent: str}`); `inspect` returns `{decision: "refine"|"finish", reason: str}`; `finalize` returns `{prose: str, chart: {...}, table_ref: str}`. Few-shot examples of schema-only reasoning are embedded in the prompts.

---

## Tools & Tool Calling

The agent does not use LLM-driven tool-calling; nodes call these helpers deterministically. Listed for completeness:

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `profiler.profile(df)` | Schema, dtypes, ranges, quality flags | DataFrame | profile dict (no raw rows) | none |
| `executor.run(code, frames)` | Runs generated pandas in a restricted namespace on the full DataFrame | code str, `{name: df}` | `{result_repr, result_obj_summary, stdout, error}` | none (read-only on df) |
| `payload.build(...)` | **Privacy gate** — assembles the LLM prompt from schema + aggregates ONLY | profile, code, result summary | prompt str | raises if a raw-row object is passed |
| `db.write_step(...)` | Persists a `run_steps` audit row | step fields | step id | DB write |

**Tool selection strategy:** rule-based — each node calls exactly the helper its phase needs. No LLM tool routing.

**Tool failure handling:** `executor.run` never raises on user-code errors — it captures the traceback into `error`, which the `inspect` node reads to decide a refine. A refine on an execution error counts against the step limit.

---

## Code Execution Sandbox (privacy + safety core)

`executor.run` executes generated pandas code with:
- **AST allow-list:** parse the code; reject `Import`/`ImportFrom`, attribute access to dunder/`os`/`sys`/`subprocess`/`open`/`eval`/`exec`/`__builtins__` escapes. Reject if disallowed nodes present (returns an `error` the agent can refine against).
- **Restricted namespace:** globals expose only `pd`, `np`, and the dataset frame(s) (`df`, or named frames in Phase 3). `__builtins__` is replaced with a curated safe subset (no `open`, `eval`, `exec`, `__import__`).
- **Full-data execution:** runs against the complete in-memory DataFrame — never a sample — so aggregates are correct.
- **Output capture:** the code must assign its answer to `result`; the executor returns a compact summary of `result` (shape, head of an *aggregate* result, scalar values) — this summary is what `inspect`/`finalize` see. The privacy gate asserts the summary is an aggregate/derived object, not a slice of raw input rows of meaningful size (results are capped and are computed outputs, never `df.head()` of raw data forwarded to the LLM).

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                      # set at initialisation
    dataset_id: str                  # set at initialisation

    # Input
    question: str                    # the user's current question
    messages: list                   # prior turns: [{role, content}] — conversation memory within session
    profile: dict                    # schema/dtypes/ranges/quality flags (NO raw rows)

    # Pipeline data (populated progressively)
    plan: str                        # strategy from `plan` node
    code: str                        # latest generated pandas code
    exec_result: dict                # {result_repr, summary, stdout, error} from executor
    step_index: int                  # current iteration (for step counter)
    max_steps: int                   # bounded loop limit (env AGENT_MAX_STEPS, default 6)
    needs_clarification: bool        # set by `plan` if question is ambiguous
    clarifying_question: str | None

    # Output
    prose: str                       # final prose answer
    chart: dict | None               # chart spec for the frontend
    table: dict | None               # results table (columns + rows of the AGGREGATE result)
    tokens: dict                     # {prompt, completion} cumulative
    cost_usd: float                  # cumulative for this run

    # Control
    error: str | None                # fatal failure → handle_error
    status: str                      # "completed" | "failed" | "needs_clarification"
```

---

## Nodes / Steps

### `node_plan`
**Reads:** `question`, `profile`, `messages`. **Writes:** `plan`, `needs_clarification`, `clarifying_question`, `step_index`.
**LLM:** yes — sees schema/profile + conversation only. Decides a strategy OR flags ambiguity (clarify-first).
**Behaviour:** If the question is ambiguous given the schema, set `needs_clarification=True` and a `clarifying_question`. Otherwise write a short plan. Increments the step counter.

### `node_clarify`
**Reads:** `clarifying_question`. **Writes:** `status="needs_clarification"`.
**LLM:** no. Emits the clarifying question as the run's answer and ends the run (the user replies as a new turn). This is the human-in-the-loop checkpoint.

### `node_generate_code`
**Reads:** `plan`, `profile`, `exec_result` (if refining). **Writes:** `code`, `step_index`.
**LLM:** yes (schema + prior error/summary only). Produces pandas code that assigns to `result`.

### `node_execute`
**Reads:** `code`, dataset frame (from `DatasetStore`, NOT from state). **Writes:** `exec_result`.
**LLM:** no. Runs `executor.run` against the full DataFrame. Captures result summary or error. **No raw rows enter state beyond the capped aggregate summary.**

### `node_inspect`
**Reads:** `exec_result`, `plan`, `step_index`, `max_steps`. **Writes:** decision (via edge), `step_index`.
**LLM:** yes (sees code + result summary/error only). Returns `refine` or `finish`. Forces `finish` (or error) when `step_index >= max_steps`.

### `node_finalize`
**Reads:** `exec_result`, `question`, `plan`. **Writes:** `prose`, `chart`, `table`, `status="completed"`, `tokens`, `cost_usd`.
**LLM:** yes (result summary only). Composes prose, picks a chart type + builds the chart/table spec from the aggregate result, attaches the exact `code`.

### `node_handle_error`
**Reads:** `error`, `run_id`. **Writes:** `status="failed"`. Updates the `runs` row, logs with `run_id`.

Every node wraps its body in try/except; on a fatal exception it sets `state["error"]` and the edge routes to `handle_error`. Every node also emits an SSE step event and persists a `run_steps` row via the streaming runner.

---

## Graph / Flow Topology

```
START
  │
  ▼
node_plan ──(error)──────────────► node_handle_error ──► END
  │
  ├──(needs_clarification)──► node_clarify ──► END
  │
  ▼
node_generate_code ──(error)─────► node_handle_error
  │
  ▼
node_execute
  │
  ▼
node_inspect ──(error)───────────► node_handle_error
  │
  ├──(refine & step<max)──► node_generate_code   (loop)
  │
  └──(finish | step>=max)──► node_finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| node_plan | `state["error"]` | node_handle_error |
| node_plan | `state["needs_clarification"]` | node_clarify |
| node_plan | else | node_generate_code |
| node_generate_code | `state["error"]` | node_handle_error |
| node_generate_code | else | node_execute |
| node_execute | (unconditional) | node_inspect |
| node_inspect | `state["error"]` | node_handle_error |
| node_inspect | decision=="refine" and step_index<max_steps | node_generate_code |
| node_inspect | decision=="finish" or step_index>=max_steps | node_finalize |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph state | plan, code, exec result, counters |
| Across runs | SQLite (`runs`, `run_steps`) + `DatasetStore` | audit history; loaded DataFrame cached per dataset |
| Conversation | `messages` in state, seeded from prior runs of the same session/dataset | prior Q&A turns — enables follow-ups like "now break that down by region" |

**Context window management:** only the profile (schema/dtypes/ranges) + the latest code + the capped result summary + recent conversation turns are sent. Raw data is never in the prompt, so the window stays small regardless of file size. Older turns are truncated to the last N (env-configurable).

---

## Human-in-the-Loop Checkpoints

| Checkpoint | Shown to user | Expected action | Timeout / default |
|------------|---------------|-----------------|-------------------|
| Clarify-first | The clarifying question (when `node_plan` flags ambiguity) | User answers as a new turn | none — run ends, user replies when ready |

---

## Error Handling & Recovery

**Node-level:** each node catches its own exceptions; fatal errors set `state["error"]` and route to `handle_error`. User-code execution errors are NOT fatal — they're fed to `inspect` to drive a refine.

**Graph-level (handle_error node):** reads `state.error`, `state.run_id`; updates the `runs` row → status `failed`, `error_message`, `completed_at`; logs with `run_id`; terminates.

**Resume / retry strategy:** runs are not resumed (short-lived, ~30s). A failed run's partial steps stay in history; the user simply re-asks.

**Partial failure:** if the step limit is hit before a clean finish, `finalize` still runs on the best available result and the answer is flagged with an uncertainty note ("hit step limit — here's the best result").

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| Trace | One logical run; one structured log line per node + one `run_steps` row | structlog stdout + SQLite |
| LLM calls | prompt/completion tokens, latency, model, cost | structlog + accumulated into `runs.tokens`/`runs.cost_usd` |
| Tool calls | executor: code hash, success/error, latency | structlog |
| Run outcome | status, total duration, error | SQLite `runs` + structlog |

LangSmith is not used (Gemini stack). Structured logs + DB audit are wired in Phase 1.

---

## Concurrency Model

- **Run isolation:** single local user; runs are scoped by `run_id` and `dataset_id`. The streaming `/ask` handles one run per request; concurrent asks on the same dataset share the cached DataFrame (read-only) safely.
- **Parallel nodes within a run:** none — the loop is inherently sequential.
- **Checkpointing:** none (runs are short; no resume needed). LangGraph compiled without a checkpointer.

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)
graph.add_node("plan", node_plan)
graph.add_node("clarify", node_clarify)
graph.add_node("generate_code", node_generate_code)
graph.add_node("execute", node_execute)
graph.add_node("inspect", node_inspect)
graph.add_node("finalize", node_finalize)
graph.add_node("handle_error", node_handle_error)

graph.set_entry_point("plan")

graph.add_conditional_edges("plan", route_after_plan, {
    "handle_error": "handle_error",
    "clarify": "clarify",
    "generate_code": "generate_code",
})
graph.add_conditional_edges("generate_code", route_after_generate, {
    "handle_error": "handle_error", "execute": "execute",
})
graph.add_edge("execute", "inspect")
graph.add_conditional_edges("inspect", route_after_inspect, {
    "handle_error": "handle_error",
    "generate_code": "generate_code",   # refine loop
    "finalize": "finalize",
})
graph.add_edge("finalize", END)
graph.add_edge("clarify", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
