# Agent

## Agent Architecture Pattern

**Chosen:** LangGraph Graph (Prompt Chaining + LLM-Generated Code Execution + Exception Handling and Recovery + Observability)

The task has a fixed, ordered sequence of steps with a conditional error branch at each step: load data → plan code → execute locally → reason over result → finalize. This is a prompt chain (#1) anchored in LLM-generated code execution (#22), not a ReAct loop — there are no dynamic tool choices; the pipeline is deterministic given input. Exception handling (#12) wraps every node; observability (#19) is wired from Phase 1 via LangSmith. LangGraph is the right fit because it provides typed state, conditional edges, and native LangSmith tracing integration.

---

## LLM Provider & Model

| Node | Provider | Model ID | Rationale |
|------|----------|----------|-----------|
| `plan_analysis` | Google Gemini | `gemini-2.5-flash` (env: `AGENT_LLM_MODEL_PLAN`) | Low latency; code generation task is well-bounded — flash is sufficient |
| `reason_answer` | Google Gemini | `gemini-2.5-pro` (env: `AGENT_LLM_MODEL_REASON`) | Higher quality reasoning over data results; user-facing answer quality matters |

**Fallback behaviour:** On a transient Gemini API error (HTTP 429, 503, or network timeout), the node retries up to 2 times with exponential backoff (1 s, 2 s). After retries exhausted, the node sets `state["error"]` and the graph routes to `handle_error`. The run status is set to `"failed"` in the DB. No silent fallback to a stub LLM — the error is surfaced to the user.

**Prompt strategy:**
- `plan_analysis`: System prompt in `src/prompts/plan_analysis.md`. User message contains schema_info (column names, dtypes, 3-row sample as JSON) + question. Output requested as JSON: `{"code_type": "pandas", "code": "..."}`. JSON mode enforced.
- `reason_answer`: System prompt in `src/prompts/reason_answer.md`. User message contains question + result sample (≤500 rows as CSV string) + column dtypes. Output requested as JSON: `{"answer_text": "...", "chart_spec": {...}}`. JSON mode enforced. Chart spec follows the schema defined in `spec/architecture.md` → Chart Pipeline.

---

## Tools & Tool Calling

This agent does not use LLM function-calling tools. The tool-use is implemented as deterministic graph nodes: `load_dataset` and `execute_code` are pure Python functions that the graph calls at fixed positions in the pipeline. The LLM in `plan_analysis` generates code as text; the graph node executes it.

| Local operation | Description | Inputs | Output | Side-effects |
|-----------------|-------------|--------|--------|--------------|
| `load_dataset` | Read CSV/Excel from local FS into DataFrame | `file_path: str`, `source_type: str` | `df: DataFrame`, `schema_info: dict` | None (read-only) |
| `execute_code` | Run LLM-generated Pandas code in sandbox | `df: DataFrame`, `generated_code: str` | `result_df: DataFrame \| scalar` | None (no I/O in sandbox) |
| `finalize` (DB write) | Persist `AnalysisRun` record to SQLite | `run_id`, `answer_text`, `chart_spec_json`, `status` | None | SQLite write |

---

## Agent State

```python
from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    # --- Identity ---
    run_id: str               # UUID; set by runner before graph invocation
    session_id: str | None    # Optional session grouping for multi-turn (Phase 3)

    # --- Input ---
    file_id: str              # SQLite uploaded_files.id; set by runner
    question: str             # User's plain-English question; set by runner
    source_type: str          # "csv" | "excel" | "postgres" (Phase 2); set by load_dataset

    # --- Pipeline data (populated progressively by nodes) ---
    file_path: str            # Absolute path on local FS; set by load_dataset
    df: Any                   # pandas.DataFrame loaded from file; set by load_dataset
    schema_info: dict         # {columns: [...], dtypes: {...}, sample_rows: [[...]]}; set by load_dataset
    generated_code: str       # Pandas code string from plan_analysis LLM call
    code_type: str            # "pandas" | "sql"; set by plan_analysis
    result_sample: str        # ≤500 rows of execution result as CSV string; set by execute_code

    # --- Output ---
    answer_text: str          # Final text answer for the user; set by reason_answer
    chart_spec: dict | None   # Plotly chart spec JSON; set by reason_answer; None if no chart applicable

    # --- Phase 3 extension ---
    conversation_history: list  # [{question, answer_text, chart_spec}, ...] prior turns in session

    # --- Control ---
    error: str | None         # Set by any node on failure; routes graph to handle_error
    status: str               # "pending" | "running" | "completed" | "failed"; updated by finalize/handle_error
```

---

## Nodes / Steps

### `load_dataset`

**Reads from state:** `file_id`, `source_type` (defaults to "csv")

**Writes to state:** `file_path`, `df`, `schema_info`, `source_type`, `error` (on failure)

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (app DB) | `SELECT file_path FROM uploaded_files WHERE id = file_id` | Set `error`; route to `handle_error` |
| Local filesystem | `pandas.read_csv(file_path)` or `pandas.read_excel(file_path)` | Set `error`; route to `handle_error` |
| PostgreSQL (Phase 2) | `psycopg2.connect(POSTGRES_DSN)` + `cursor.execute(introspection SQL)` | Set `error`; route to `handle_error` |

**Behaviour:** Looks up `file_path` from the SQLite `uploaded_files` table using `file_id`. Reads the file into a pandas DataFrame. Extracts `schema_info`: column names, dtype string per column, and the first 3 rows as a list of lists. Stores all three fields in state. If the file does not exist or the SQLite record is missing, sets `error` and returns — the conditional edge routes to `handle_error`. In Phase 2, when `source_type == "postgres"`, opens a `psycopg2` connection, introspects the named table's schema, and stores the connection handle and schema in state instead of a DataFrame.

---

### `plan_analysis`

**Reads from state:** `schema_info`, `question`, `conversation_history` (Phase 3)

**Writes to state:** `generated_code`, `code_type`, `error` (on failure)

**LLM call:** Yes — `gemini-2.5-flash` (`AGENT_LLM_MODEL_PLAN`)

System prompt: `src/prompts/plan_analysis.md`. Instructs the model to output only valid JSON with keys `code_type` and `code`. The code must use variable `df` (already in scope) and assign its final result to a variable named `result`. Forbidden in code: `import os`, `import sys`, `import subprocess`, `open(`, `socket`, `requests`, `urllib`. Result must be a DataFrame or a scalar.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Chat completion with JSON output mode | Retry ×2 with backoff; then set `error` |

**Behaviour:** Sends the schema info and question to the Gemini flash model. Parses the JSON response to extract `code_type` and `code`. Performs a static AST check on the generated code to block any forbidden imports before storing it in state. If the LLM response is not valid JSON, or the AST check fails, sets `error` and returns.

---

### `execute_code`

**Reads from state:** `df`, `generated_code`, `code_type`

**Writes to state:** `result_sample`, `error` (on failure)

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Local exec() sandbox | `exec(generated_code, restricted_globals)` | Catch exception; set `error` |
| PostgreSQL (Phase 2) | `cursor.execute(generated_code)` (when `code_type == "sql"`) | Catch exception; set `error` |

**Behaviour:** Constructs a restricted globals dict: `{"df": df, "pd": pandas, "__builtins__": <whitelist>}`. The whitelist includes: `len`, `range`, `enumerate`, `zip`, `sorted`, `min`, `max`, `sum`, `abs`, `round`, `str`, `int`, `float`, `list`, `dict`, `tuple`, `bool`, `print`. Runs `exec(generated_code, restricted_globals)` inside a `concurrent.futures.ThreadPoolExecutor` with a 30-second timeout. After execution, reads `restricted_globals["result"]`. If `result` is a DataFrame, samples to at most 500 rows and serializes to CSV string (`result.head(500).to_csv(index=False)`). If `result` is a scalar, converts to string. Stores in `result_sample`. On any exception (including timeout), sets `error` with the exception message. In Phase 2, when `code_type == "sql"`, runs the SQL via psycopg2 instead, fetches up to 500 rows, and serializes to CSV.

---

### `reason_answer`

**Reads from state:** `question`, `result_sample`, `schema_info`, `conversation_history` (Phase 3)

**Writes to state:** `answer_text`, `chart_spec`, `error` (on failure)

**LLM call:** Yes — `gemini-2.5-pro` (`AGENT_LLM_MODEL_REASON`)

System prompt: `src/prompts/reason_answer.md`. Instructs the model to output only valid JSON with keys `answer_text` (plain-English answer) and `chart_spec` (Plotly figure JSON or null). Chart type selection rules are included in the system prompt (bar/line/scatter/pie selection logic as specified in `spec/architecture.md`).

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Chat completion with JSON output mode | Retry ×2 with backoff; then set `error` |

**Behaviour:** Sends the original question, the result sample CSV, and schema info (column dtypes) to the Gemini pro model. Parses the JSON response. Validates `chart_spec` against the required schema (must have `data` array and `layout` object if non-null). Stores `answer_text` and `chart_spec` in state. If the LLM response cannot be parsed as valid JSON, sets `error` and returns. Null `chart_spec` is valid (text-only answer for scalar results).

---

### `handle_error`

**Reads from state:** `error`, `run_id`

**Writes to state:** `status` = `"failed"`

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (app DB) | Update `analysis_runs.status` = "failed", `error_message` = `state["error"]` | Log only; do not raise |
| structlog | Log error with `run_id` and `error` fields | Never raises |

**Behaviour:** Logs the error with context. Attempts to persist the error to the `analysis_runs` table. Sets `status = "failed"` in state. Always routes to END — never re-raises.

---

### `finalize`

**Reads from state:** `run_id`, `answer_text`, `chart_spec`, `file_id`, `question`

**Writes to state:** `status` = `"completed"`

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (app DB) | `INSERT/UPDATE analysis_runs` with `answer_text`, `chart_spec_json`, `status="completed"` | Log + set `error`; status becomes "failed" |

**Behaviour:** Serializes `chart_spec` to JSON string. Upserts the `AnalysisRun` record in SQLite. Sets `status = "completed"` in state. Structured log emitted with run summary (run_id, file_id, question truncated to 100 chars, status, latency).

---

## Graph / Flow Topology

```
START
  │
  ▼
load_dataset ──(error set)──────────────────────────────► handle_error ──► END
  │
  ▼
plan_analysis ──(error set)─────────────────────────────► handle_error ──► END
  │
  ▼
execute_code ──(error set)──────────────────────────────► handle_error ──► END
  │
  ▼
reason_answer ──(error set)─────────────────────────────► handle_error ──► END
  │
  ▼
finalize ──────────────────────────────────────────────────────────────────► END
```

**Conditional edges:**

| Source node | Routing function | Condition | Target |
|-------------|-----------------|-----------|--------|
| `load_dataset` | `after_load` | `state.get("error")` is truthy | `handle_error` |
| `load_dataset` | `after_load` | no error | `plan_analysis` |
| `plan_analysis` | `after_plan` | `state.get("error")` is truthy | `handle_error` |
| `plan_analysis` | `after_plan` | no error | `execute_code` |
| `execute_code` | `after_execute` | `state.get("error")` is truthy | `handle_error` |
| `execute_code` | `after_execute` | no error | `reason_answer` |
| `reason_answer` | `after_reason` | `state.get("error")` is truthy | `handle_error` |
| `reason_answer` | `after_reason` | no error | `finalize` |

`finalize` and `handle_error` both have unconditional edges to `END`.

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph `AgentState` (in-memory TypedDict) | All pipeline data: df, schema, code, result_sample, answer, chart_spec |
| Across runs (same session) | SQLite `analysis_runs` + `AgentState.conversation_history` (Phase 3) | Prior question/answer/chart_spec turns loaded at graph start |
| Across sessions | SQLite `uploaded_files` (schema_json) | File registry and schema persisted so files don't need re-uploading (Phase 2) |

**Context window management:** The result sample is hard-capped at 500 rows serialized as CSV. The schema_info sample is the first 3 rows only. The conversation history (Phase 3) is capped at the last 5 turns to avoid token overflow.

---

## Human-in-the-Loop Checkpoints

None. This is a fully automated pipeline — the user submits a question and receives an answer. No approval steps are required.

---

## Error Handling & Recovery

**Node-level:** Every node wraps its logic in `try/except Exception`. On any exception, the node sets `state["error"] = str(exc)` and returns immediately. The conditional edge after that node routes to `handle_error`.

**Graph-level (`handle_error` node):**
- Reads: `state["error"]`, `state["run_id"]`
- Updates SQLite: `analysis_runs.status = "failed"`, `analysis_runs.error_message = state["error"]`
- Emits a structured log line at ERROR level: `{"event": "run_failed", "run_id": ..., "error": ...}`
- Returns `{**state, "status": "failed"}` and the graph terminates at END

**Resume / retry strategy:** No cross-run resume. Each `POST /api/analysis/run` call starts a fresh graph invocation. Within-node retries (up to 2 for LLM calls) are the only retry mechanism.

**Partial failure:** Execution failures in `execute_code` (e.g. the LLM-generated code raises a NameError) are treated as fatal for that run — the agent does not attempt to regenerate code. This is intentional for Phase 1/2; Phase 3 may add a retry-with-feedback loop.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| LangSmith trace | One trace per `agentic_ai.invoke()` call; one span per node with inputs/outputs | LangSmith dashboard (when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` set) |
| Structured log — run start | `{"event": "run_start", "run_id": ..., "file_id": ..., "question": ...}` | stdout via structlog |
| Structured log — LLM call | `{"event": "llm_call", "node": ..., "model": ..., "latency_ms": ...}` | stdout via structlog |
| Structured log — exec | `{"event": "code_exec", "result_rows": ..., "latency_ms": ...}` | stdout via structlog |
| Structured log — run end | `{"event": "run_end", "run_id": ..., "status": ..., "total_latency_ms": ...}` | stdout via structlog |

LangSmith env vars are in `Settings` under the `AGENT_` prefix: `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY`. The `langchain-core` package is imported and tracing is auto-enabled by LangGraph when the env vars are set.

> **Assumed:** `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` are read as bare env vars (no `AGENT_` prefix) by the LangChain/LangGraph SDK itself. The `Settings` class adds `langchain_api_key: str = Field(default="")` for reference but the SDK reads `LANGCHAIN_API_KEY` directly from the environment. Both the `.env` doc and the README must document both `AGENT_GEMINI_API_KEY` and `LANGCHAIN_API_KEY` (no prefix on the latter).

---

## Concurrency Model

- **Run isolation:** Concurrent runs are fully isolated by `run_id` (UUID). Each graph invocation has its own `AgentState` dict. SQLite writes use per-session transactions.
- **Parallel nodes within a run:** None. The pipeline is strictly sequential (load → plan → execute → reason → finalize). No parallel node execution.
- **Checkpointing:** None. LangGraph's default in-memory checkpointer is sufficient — runs are short (< 60 s). No `SqliteSaver` or `PostgresSaver` required.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.nodes import (
    load_dataset,
    plan_analysis,
    execute_code,
    reason_answer,
    handle_error,
    finalize,
)
from graph.edges import (
    after_load,
    after_plan,
    after_execute,
    after_reason,
)


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("load_dataset", load_dataset)
    g.add_node("plan_analysis", plan_analysis)
    g.add_node("execute_code", execute_code)
    g.add_node("reason_answer", reason_answer)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("load_dataset")

    g.add_conditional_edges(
        "load_dataset",
        after_load,
        {"plan_analysis": "plan_analysis", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "plan_analysis",
        after_plan,
        {"execute_code": "execute_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code",
        after_execute,
        {"reason_answer": "reason_answer", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "reason_answer",
        after_reason,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
```

**Edge routing functions** (`src/graph/edges.py`):

```python
def after_load(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "plan_analysis"

def after_plan(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "execute_code"

def after_execute(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "reason_answer"

def after_reason(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "finalize"
```
