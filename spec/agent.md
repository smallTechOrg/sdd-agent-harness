# Agent

## Agent Architecture Pattern

**Chosen: Graph (LangGraph) + ReAct-style reasoning loop**

The agent uses a LangGraph `StateGraph` with a conditional back-edge that implements a ReAct (Reason → Act → Observe) loop. Each iteration writes Python code, executes it in a sandboxed subprocess, and inspects the result. If the result is unsatisfactory and fewer than 5 iterations have been used, the graph re-enters `plan_steps` with revised context. This pattern is chosen because data analysis questions require iterative refinement — the first code attempt often needs adjustment based on actual data shapes or errors.

Patterns in use (see `harness/patterns/agentic-ai.md`):
- **#5 Tool Use** — the agent calls `execute_code` (subprocess) as its primary tool.
- **#17 ReAct Reasoning** — reason (plan) → act (execute) → observe (inspect) loop.
- **#12 Exception Handling and Recovery** — each node catches errors; `handle_error` node surfaces failure gracefully.
- **#19 Evaluation and Monitoring** — structured logs per query; LangSmith tracing enabled via env vars.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan_steps` | Google Gemini | `gemini-2.5-flash` | Needs strong code-generation quality; Flash is sufficient and fast |
| `inspect_result` | Google Gemini | `gemini-2.5-flash` | Binary quality judgment; Flash is fast and cheap per call |
| `synthesize_answer` | Google Gemini | `gemini-2.5-flash` | Narrative generation + chart selection; Flash quality is adequate |
| `suggest_followups` (Phase 3) | Google Gemini | `gemini-2.5-flash` | Simple suggestion task; Flash |

Model ID resolved from `AGENT_LLM_MODEL` env var (default `gemini-2.5-flash`). All nodes share the same `GeminiClient` instance.

**Fallback behaviour:** Each LLM call retries up to 3 times with exponential back-off (1 s, 2 s, 4 s) on `429 RateLimitError` or `503 ServiceUnavailable`. After 3 failures the node sets `state["error"]` and the graph routes to `handle_error`. No silent degradation.

**Prompt strategy:** Each node uses a dedicated system prompt loaded from `src/data_analysis/prompts/<node_name>.md`. LLM calls use structured JSON output (Gemini `response_schema`) for `plan_steps` (plan as a structured list) and `synthesize_answer` (answer text + Plotly spec). `inspect_result` uses a simple boolean + explanation response. All prompts include the data profile as context.

---

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_code` | Writes Python code to a temp file and runs it in a subprocess with a 30 s timeout | `code: str`, `data_paths: list[str]`, `iteration: int` | `ExecutionResult(stdout: str, stderr: str, success: bool, elapsed_s: float)` | Creates and deletes a temp `.py` file; reads from `uploads/` |
| `load_profile` | Reads the cached profile JSON for a given `file_id` from SQLite | `file_id: str` | `FileProfile` (see data model) | None (read-only) |
| `save_query_run` | Writes a `query_runs` row to SQLite with status, tokens, cost, and timing | `QueryRunRecord` | `None` | DB write |
| `join_files` (Phase 2) | Loads two DataFrames and performs a pandas merge on a shared column | `file_ids: list[str]`, `join_column: str`, `how: str` | `pd.DataFrame` | None |

**Tool selection strategy:** The LLM does not choose tools; the graph topology enforces which tool each node calls. `plan_steps` always LLM-plans; `execute_code` always calls the subprocess tool; `inspect_result` always LLM-inspects. No LLM-driven tool dispatch.

**Tool failure handling:**
- `execute_code` timeout (>30 s): treated as a failed iteration (sets `last_execution_error`); graph back-edges to `plan_steps` if iterations remain, else to `handle_error`.
- `execute_code` non-zero exit code: treated as a failed iteration; stderr passed to `plan_steps` as context for the next attempt.
- `load_profile` failure: sets `state["error"]`; routes to `handle_error`.
- `save_query_run` failure: logged; query result is still streamed (degraded persistence).

---

## Agent State

```python
class AnalysisState(TypedDict):
    # Identity
    query_run_id: str                    # UUID, set at graph entry

    # Input
    question: str                        # user's natural-language question
    file_ids: list[str]                  # one or more uploaded file IDs
    session_id: str | None              # optional session for history (Phase 2)

    # Data context
    profiles: list[FileProfile]         # populated by profile_data node
    data_paths: list[str]               # local filesystem paths to uploaded files

    # Reasoning loop
    plan: str                           # current pandas/DuckDB plan (plain text)
    iteration: int                      # current loop count, starts at 0
    max_iterations: int                 # hard limit, default 5
    execution_history: list[ExecutionStep]  # all (code, stdout, stderr) per iteration
    last_execution_result: ExecutionResult | None  # most recent subprocess result
    last_execution_error: str | None    # stderr of most recent failure

    # Clarification branch (human-in-the-loop)
    needs_clarification: bool           # set by plan_steps if question is ambiguous
    clarification_question: str | None  # question to show the user

    # Output
    answer_text: str | None             # synthesized plain-text answer
    plotly_chart: dict | None           # Plotly figure spec (JSON-serialisable dict)
    followup_suggestions: list[str]     # Phase 3; populated by suggest_followups

    # Observability
    input_tokens: int                   # cumulative across all LLM calls in this run
    output_tokens: int                  # cumulative across all LLM calls in this run
    cost_usd: float                     # estimated cost, computed on completion

    # Control
    error: str | None                   # set by any node on fatal failure
    checkpoint: str | None             # last completed node name
```

`ExecutionStep` (TypedDict): `iteration: int`, `code: str`, `stdout: str`, `stderr: str`, `success: bool`, `elapsed_s: float`.

`ExecutionResult` (TypedDict): `stdout: str`, `stderr: str`, `success: bool`, `elapsed_s: float`.

`FileProfile` is defined in `spec/data.md` — it is a dict matching the `FileProfile` SQLAlchemy model's `profile_json` field.

---

## Nodes / Steps

### `profile_data`

**Reads from state:** `file_ids`, `data_paths`

**Writes to state:** `profiles`, `checkpoint`

**LLM call:** No. Uses `load_profile` tool (read from SQLite).

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | `SELECT profile_json FROM uploaded_files WHERE id = ?` | fatal — set `state["error"]`, route to `handle_error` |

**Behaviour:** For each `file_id` in `file_ids`, load the pre-computed profile JSON written at upload time. Assembles the list of `FileProfile` dicts into `state["profiles"]`. If any file_id is not found, sets `state["error"]` with a user-readable message.

---

### `plan_steps`

**Reads from state:** `question`, `profiles`, `execution_history`, `last_execution_error`, `iteration`

**Writes to state:** `plan`, `needs_clarification`, `clarification_question`, `checkpoint`, `input_tokens`, `output_tokens`

**LLM call:** Yes. Prompt: system prompt from `prompts/plan_steps.md` + serialised profiles + question + prior execution history (last 2 steps). Structured JSON output: `{plan: str, needs_clarification: bool, clarification_question: str | null}`. Model: `gemini-2.5-flash`.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Chat completion with structured output | retry 3× then set `state["error"]` |

**Behaviour:** Given the user question, data profiles, and any prior failed attempts (with their stderr), produce a step-by-step plan describing what Python/pandas/DuckDB code to write next. If the question is genuinely ambiguous (e.g., a column name collision) and this is `iteration == 0`, set `needs_clarification = True` and populate `clarification_question`. On subsequent iterations (retry after failure), never set `needs_clarification`.

---

### `execute_code`

**Reads from state:** `plan`, `data_paths`, `iteration`

**Writes to state:** `execution_history`, `last_execution_result`, `last_execution_error`, `checkpoint`

**LLM call:** No. Calls `execute_code` tool (subprocess).

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| OS subprocess | Write temp `.py`, run `python <file>` with 30 s timeout | on timeout: mark `success=False`, populate `stderr="TimeoutError"` |

**Behaviour:** Translates the current `plan` into executable Python code using a fixed code template (imports pandas, DuckDB, outputs result as JSON to stdout). Writes to a temp file in `/tmp/data_analysis_<run_id>_iter<N>.py`. Runs it in a subprocess with `subprocess.run(..., timeout=30)`. Captures stdout and stderr. Appends an `ExecutionStep` to `execution_history`. Never calls `exec()` or `eval()`.

---

### `inspect_result`

**Reads from state:** `last_execution_result`, `question`, `profiles`, `iteration`

**Writes to state:** `checkpoint`, `input_tokens`, `output_tokens`

**LLM call:** Yes. Prompt: "Given this question and this execution result (stdout/stderr), is the result complete and correct? Answer JSON: `{complete: bool, explanation: str}`." Model: `gemini-2.5-flash`.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Short classification completion | retry 3× then treat as `complete: false` (conservative — loops again if iterations remain) |

**Behaviour:** Evaluates the stdout of the most recent code execution. If the execution failed (`success == False`), always returns `complete: false`. If the stdout is empty or clearly incomplete (e.g., only an error trace), returns `complete: false`. Otherwise returns `complete: true` with an explanation. Does not modify the answer — that is `synthesize_answer`'s job.

---

### `synthesize_answer`

**Reads from state:** `question`, `profiles`, `execution_history`, `last_execution_result`

**Writes to state:** `answer_text`, `plotly_chart`, `input_tokens`, `output_tokens`, `cost_usd`, `checkpoint`

**LLM call:** Yes. Prompt: system prompt from `prompts/synthesize_answer.md` + question + profiles + best execution result. Structured JSON output: `{answer_text: str, plotly_chart: dict}`. The Plotly spec must be a valid `plotly.graph_objects.Figure`-compatible dict. Model: `gemini-2.5-flash`.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Long-form structured completion | retry 3× then set `state["error"]` |

**Behaviour:** Produces a concise narrative answer to the user's question, grounded in the actual execution output. Selects the most appropriate Plotly chart type for the data (bar, line, scatter, histogram, heatmap, pie — chosen by the LLM based on data shape). Computes `cost_usd` from cumulative `input_tokens` + `output_tokens` using the rate constants in `Settings`. Emits tokens to the SSE stream incrementally via a callback registered in the runner.

---

### `suggest_followups` (Phase 3 only)

**Reads from state:** `question`, `answer_text`, `profiles`

**Writes to state:** `followup_suggestions`, `input_tokens`, `output_tokens`, `checkpoint`

**LLM call:** Yes. Returns a JSON array of 2–3 follow-up question strings. Model: `gemini-2.5-flash`.

**External calls:** Gemini API only; same retry policy.

**Behaviour:** Given the question just answered and the data profiles, generate 2–3 natural follow-up questions the user might want to ask next. Returns them as `list[str]` with a max of 3 items. Called after `synthesize_answer`, before the SSE stream closes.

---

### `handle_error`

**Reads from state:** `error`, `query_run_id`

**Writes to state:** Nothing (terminal node).

**LLM call:** No.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | `UPDATE query_runs SET status='failed', error_message=? WHERE id=?` | log only |

**Behaviour:** Logs the error with `query_run_id` context via structlog. Updates the `query_runs` row to `status='failed'`. Emits a final SSE event `{"type":"error","message":state["error"]}` so the browser can render a user-readable failure message. Terminates the graph.

---

## Graph / Flow Topology

```
START
  │
  ▼
profile_data ──(error)──────────────────────────────────────► handle_error ──► END
  │
  ▼
plan_steps ──(error)────────────────────────────────────────► handle_error ──► END
  │
  ├──(needs_clarification=True)──► stream_clarification ──► END (awaits user reply)
  │
  ▼
execute_code ──(error)──────────────────────────────────────► handle_error ──► END
  │
  ▼
inspect_result ──(error)────────────────────────────────────► handle_error ──► END
  │
  ▼
decide_continue ──(complete=True  OR  iteration≥max_iterations)──► synthesize_answer
  │
  └──(complete=False AND iteration<max_iterations)──► plan_steps  (back-edge: loop)
                                                           ↑ increments iteration

synthesize_answer ──(error)─────────────────────────────────► handle_error ──► END
  │
  ▼   [Phase 3: add suggest_followups here]
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `profile_data` | `state["error"] is not None` | `handle_error` |
| `profile_data` | `state["error"] is None` | `plan_steps` |
| `plan_steps` | `state["error"] is not None` | `handle_error` |
| `plan_steps` | `state["needs_clarification"] is True` AND `state["iteration"] == 0` | `stream_clarification` |
| `plan_steps` | otherwise | `execute_code` |
| `execute_code` | `state["error"] is not None` | `handle_error` |
| `execute_code` | otherwise | `inspect_result` |
| `inspect_result` | `state["error"] is not None` | `handle_error` |
| `inspect_result` | otherwise | `decide_continue` |
| `decide_continue` | `last_execution_result["complete"] is True` OR `state["iteration"] >= state["max_iterations"]` | `synthesize_answer` |
| `decide_continue` | `last_execution_result["complete"] is False` AND `state["iteration"] < state["max_iterations"]` | `plan_steps` (increments `iteration`) |
| `synthesize_answer` | `state["error"] is not None` | `handle_error` |
| `synthesize_answer` | otherwise | `finalize` |

`decide_continue` is a pure-Python edge function (no LLM call); it reads `inspect_result`'s stored output from the last `ExecutionStep` and `state["iteration"]`.

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph `AnalysisState` | All plan/code/result/answer data for the current query |
| **Across runs (same session)** | SQLite `query_runs` table | Question, answer, tokens, cost, timing per query |
| **Across sessions** | SQLite `sessions` table (Phase 2) | Session name, created_at, associated file IDs |
| **File data** | Filesystem `uploads/` + SQLite `uploaded_files` | Raw file bytes + profile JSON |

**Context window management:** The `plan_steps` prompt includes only the last 2 `ExecutionStep` entries from `execution_history` (not the full history), keeping the prompt within Gemini's 1M token context window. Data profiles are summarised (column names, types, row count, first 3 sample rows) rather than including full file contents.

---

## Human-in-the-Loop Checkpoints

| Checkpoint | What is shown to the user | Expected user action | Timeout / default |
|------------|--------------------------|----------------------|-------------------|
| `stream_clarification` | A clarifying question from the agent (e.g., "Did you mean column X or column Y?") rendered as a chat bubble in the UI | User types a clarifying reply; it is sent as a new query with the same `file_ids` | None — the user's next message is the reply; no timeout |

---

## Error Handling & Recovery

**Node-level:** Each node wraps its logic in `try/except`. On any unexpected exception, the node sets `state["error"] = str(exception)` and returns immediately. The conditional edge routes to `handle_error`.

**Graph-level (`handle_error` node):**
- Reads: `state["error"]`, `state["query_run_id"]`
- Updates DB: `query_runs.status = "failed"`, `query_runs.error_message = state["error"]`, `query_runs.completed_at = now()`
- Emits SSE event: `{"type":"error","message":state["error"]}`
- Logs with structlog at ERROR level including `query_run_id`
- Returns normally (graph ends at `END`)

**Resume / retry strategy:** No cross-session resume. Within a single run, the back-edge to `plan_steps` is the retry mechanism (up to `max_iterations`). If the server restarts mid-run, the run is marked as `status='interrupted'` on next startup (a startup hook scans for `status='running'` rows older than 5 minutes and sets them to `'interrupted'`).

**Partial failure:** `save_query_run` DB failure is logged but does not abort the query — the answer is still streamed to the user. This is the only non-fatal partial failure.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Structured log per query** | `query_run_id`, `question` (truncated to 200 chars), `status`, `iterations_used`, `input_tokens`, `output_tokens`, `cost_usd`, `elapsed_s` | structlog → stdout |
| **Per-node log** | `node_name`, `iteration`, `success`, `elapsed_s` | structlog → stdout |
| **LLM call log** | `model`, `input_tokens`, `output_tokens`, `latency_s` | structlog → stdout |
| **Tool call log** | `tool_name`, `iteration`, `success`, `elapsed_s`, `stderr` (on failure) | structlog → stdout |
| **LangSmith tracing** | Full trace per run, one span per node | LangSmith (enabled when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set) |

LangSmith env vars: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY=<key>`, `LANGCHAIN_PROJECT=data-analysis-agent`. These are optional — the app runs without them; structured stdout logging is always active.

---

## Concurrency Model

- **Run isolation:** Each SSE connection creates a new `AnalysisState` with a unique `query_run_id` (UUID4). The user is single-user so concurrent runs are unlikely; if two requests arrive simultaneously they each get their own state and run independently (no 409).
- **Parallel nodes within a run:** None — the ReAct loop is sequential by design (each step depends on the previous result).
- **Checkpointing:** No LangGraph checkpointer (no `SqliteSaver`). The `checkpoint` field in state records the last completed node for debugging but is not used for resume.

---

## Graph Assembly (`src/data_analysis/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from .state import AnalysisState
from .nodes import (
    node_profile_data,
    node_plan_steps,
    node_execute_code,
    node_inspect_result,
    node_synthesize_answer,
    node_finalize,
    node_handle_error,
    node_stream_clarification,
)
from .edges import (
    edge_after_profile,
    edge_after_plan,
    edge_after_execute,
    edge_after_inspect,  # decide_continue logic
    edge_after_synthesize,
)

graph = StateGraph(AnalysisState)

graph.add_node("profile_data", node_profile_data)
graph.add_node("plan_steps", node_plan_steps)
graph.add_node("execute_code", node_execute_code)
graph.add_node("inspect_result", node_inspect_result)
graph.add_node("synthesize_answer", node_synthesize_answer)
graph.add_node("finalize", node_finalize)
graph.add_node("handle_error", node_handle_error)
graph.add_node("stream_clarification", node_stream_clarification)

graph.set_entry_point("profile_data")

graph.add_conditional_edges("profile_data", edge_after_profile)
graph.add_conditional_edges("plan_steps", edge_after_plan)
graph.add_conditional_edges("execute_code", edge_after_execute)
graph.add_conditional_edges("inspect_result", edge_after_inspect)   # decide_continue
graph.add_conditional_edges("synthesize_answer", edge_after_synthesize)

graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)
graph.add_edge("stream_clarification", END)

compiled_graph = graph.compile()
```

Each `edge_after_*` function is a pure-Python callable that inspects the relevant state fields and returns a node-name string matching the conditional edges table above.
