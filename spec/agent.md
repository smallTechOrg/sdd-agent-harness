# Agent

## Agent Architecture Pattern

**Chosen:** Graph (LangGraph) with Routing — a multi-node conditional pipeline that reads a file, routes to the correct analysis branch (preset pandas vs. Gemini NL), runs the analysis, and finalizes. Routing pattern (#2 from `harness/patterns/agentic-ai.md`) is combined with Tool Use / LLM-Generated Code Execution (#5, #22) on the NL path and Reflection (#4) added in Phase 4. The graph is chosen over a simple loop because the preset and NL branches need genuinely different execution paths with no branching overlap.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `run_nl_query` | Google Gemini | `gemini-2.5-pro` (env: `AGENT_LLM_MODEL`) | High-quality code generation; env-configurable |
| `reflect_nl_result` (Phase 4+) | Google Gemini | `gemini-2.5-pro` (env: `AGENT_LLM_MODEL`) | Same model for correction prompt; latency acceptable for retry path |
| All other nodes | None | N/A | Pure pandas — no LLM |

**Fallback behaviour:** If the Gemini API call in `run_nl_query` raises an exception (timeout, 4xx, 5xx), the node sets `state["error"]` with a user-readable message and the graph routes to `handle_error`. The error is persisted to the `analyses` row (status=failed, error_message set). No silent fallback — the user sees a clear error message in the browser.

**Prompt strategy:** `run_nl_query` uses a system prompt (loaded from `src/prompts/nl_query.md`) that instructs Gemini to return only valid Python/pandas code in a fenced code block, operating on a variable called `df` (the DataFrame). The user prompt includes the DataFrame schema (column names + dtypes) and up to 20 sample rows (as CSV text), followed by the user's question. Structured output is enforced by post-processing: the node extracts the first fenced code block from the response and rejects responses that contain no code block (routes to `handle_error`).

---

## Tools & Tool Calling

This agent does not use LangGraph tool-calling / function-calling. Instead, the LLM generates pandas code and the backend executes it (Pattern #22: LLM-Generated Code Execution). The "tools" are internal node functions, not LLM-callable tools.

| Internal function | Description | Inputs | Output | Side-effects |
|------------------|-------------|--------|--------|--------------|
| `_run_summary_stats(df)` | Compute mean, median, min, max, std per numeric column; distribution counts for categoricals | pandas DataFrame | `{ summary: str, chart_json: str, table: list }` | None |
| `_run_trend_over_time(df, date_col, value_col)` | Group by date_col, plot value_col as line chart | DataFrame + params | `{ summary: str, chart_json: str, table: list }` | None |
| `_run_top_bottom_n(df, col, n, direction)` | Sort by col, take top/bottom N rows | DataFrame + params | `{ summary: str, chart_json: str, table: list }` | None |
| `_run_correlation(df, col_a, col_b)` | Compute Pearson r, scatter plot | DataFrame + params | `{ summary: str, chart_json: str, table: list }` | None |
| `_execute_nl_code(code_str, df)` | Execute Gemini-generated code in restricted namespace | code string + DataFrame | result object (any pandas/primitive type) | None (read-only on df) |

**Tool failure handling:** Each internal function is wrapped in a try/except within `run_preset_analysis` or `run_nl_query`. On exception, `state["error"]` is set with the exception message and the graph routes to `handle_error`.

---

## Agent State

```python
class DataAnalysisState(TypedDict, total=False):
    # Identity
    run_id: str                    # UUID; set at analysis creation in the DB

    # Input (set before graph invocation)
    upload_id: str                 # FK to uploads table
    analysis_type: str             # "summary_stats" | "trend_over_time" | "top_bottom_n" | "correlation" | "nl_query"
    params: dict                   # analysis-specific parameters (e.g. {"col": "sales", "n": 5})
    question: str | None           # populated only for nl_query

    # Pipeline data (set by nodes during execution)
    filepath: str | None           # absolute path to uploaded file; set by parse_upload
    dataframe: object | None       # pandas DataFrame; set by parse_upload (not serialized to DB)
    generated_code: str | None     # Gemini-generated pandas code; set by run_nl_query
    nl_result_raw: object | None   # raw output of executing generated code; set by run_nl_query

    # Output (set by format_response)
    summary: str | None            # plain-English analysis summary
    chart_json: str | None         # Plotly figure JSON (serialized with plotly.io.to_json)
    table: list | None             # list of dicts [{col: val}, ...] for tabular display

    # Control
    error: str | None              # set by any node on failure; routes to handle_error
    status: str | None             # "pending" | "completed" | "failed"; written to DB by finalize
```

Note: `dataframe` is a live pandas object; it lives only in memory during graph execution and is never serialized to the database.

---

## Nodes / Steps

### `parse_upload`

**Reads from state:** `upload_id`

**Writes to state:** `filepath`, `dataframe`, `error`

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite DB | `SELECT filepath FROM uploads WHERE id = upload_id` | Set `error`; route to `handle_error` |
| Local filesystem | `pandas.read_csv` or `pandas.read_excel` on `filepath` | Set `error`; route to `handle_error` |

**Behaviour:** Looks up the upload record to get the file path, then reads the file into a pandas DataFrame. Detects file format from extension (`.csv` → `pd.read_csv`; `.xlsx`/`.xls` → `pd.read_excel`). Sets `state["dataframe"]` and `state["filepath"]`. On any exception (file not found, parse error, unsupported format), sets `state["error"]` with a user-readable message.

---

### `route_analysis` (edge function — not a node)

**Reads from state:** `analysis_type`, `error`

**Writes to state:** nothing — pure routing decision

**LLM call:** No

**External calls:** None

**Behaviour:** Implemented as `after_parse_and_route` in `src/graph/edges.py` — the conditional edge function attached to `parse_upload`. Returns `"run_preset_analysis"` if `analysis_type` is one of `summary_stats`, `trend_over_time`, `top_bottom_n`, or `correlation`. Returns `"run_nl_query"` if `analysis_type == "nl_query"`. Returns `"handle_error"` if `state.get("error")` is set (error from `parse_upload`) or if `analysis_type` is unknown. This is the branching point of the graph and is a pure function with no side effects.

---

### `run_preset_analysis`

**Reads from state:** `analysis_type`, `params`, `dataframe`

**Writes to state:** `summary`, `chart_json`, `table`, `error`

**LLM call:** No

**External calls:** None

**Phase 1 stub policy:** Only `summary_stats` is real in Phase 1. `trend_over_time`, `top_bottom_n`, and `correlation` are stubbed: they set `summary = "Coming in Phase 2"`, `chart_json = None`, `table = None` and route to `format_response`. Stubs are replaced with real pandas logic in Phase 2.

**Behaviour:** Dispatches to the appropriate internal helper function based on `analysis_type`:

- `summary_stats`: calls `_run_summary_stats(df)`. Computes mean, median, min, max, std, and count for each numeric column. For categorical columns, computes value counts. Returns a Plotly bar chart (distribution of first numeric column) as chart JSON, a summary string, and a table of stats.
- `trend_over_time`: calls `_run_trend_over_time(df, params["date_col"], params["value_col"])`. Parses the date column, groups by date, plots a Plotly line chart. Returns chart JSON, summary (date range + trend direction), and grouped table.
- `top_bottom_n`: calls `_run_top_bottom_n(df, params["col"], params["n"], params["direction"])`. Sorts DataFrame by `col`, takes top or bottom `n` rows. Returns a Plotly bar chart, summary string, and the selected rows as table.
- `correlation`: calls `_run_correlation(df, params["col_a"], params["col_b"])`. Drops NaN rows, computes Pearson r, creates a Plotly scatter plot. Returns chart JSON, summary (Pearson r value + interpretation), and a two-column sample table.

On any exception, sets `state["error"]`.

---

### `run_nl_query`

**Reads from state:** `question`, `dataframe`

**Writes to state:** `generated_code`, `nl_result_raw`, `summary`, `chart_json`, `table`, `error`

**LLM call:** Yes — Gemini `gemini-2.5-pro`

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | `generate_content` with schema + sample + question | Set `error`; route to `handle_error` |

**Phase 1 stub policy:** In Phase 1, this node is a stub that immediately sets `error = "NL query not available until Phase 3"` and routes to `handle_error`. It is replaced with real logic in Phase 3.

**Behaviour (Phase 3+):** Builds a prompt from the system prompt in `src/prompts/nl_query.md`, the DataFrame schema (column names + dtypes as a table), up to 20 sample rows (as CSV text), and the user's question. Calls Gemini. Extracts the first fenced Python code block from the response. Executes the code via `_execute_nl_code(code_str, df)` in a restricted namespace (`{"df": df, "pd": pd}` only; forbidden imports enforced; 10-second timeout via `signal.alarm` in Phase 4+). Converts the result to `summary`, `chart_json` (if the result is a Plotly figure), and `table` (if the result is a DataFrame or dict). If no fenced code block is found, sets `state["error"]`.

---

### `reflect_nl_result` (Phase 4+ only)

**Reads from state:** `question`, `dataframe`, `generated_code`, `nl_result_raw`, `error`

**Writes to state:** `generated_code`, `nl_result_raw`, `summary`, `chart_json`, `table`, `error`

**LLM call:** Yes — Gemini `gemini-2.5-pro` (only on retry path)

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Correction prompt with original code + error message | Set `error`; route to `handle_error` (no further retry) |

**Phase 1–3 stub policy:** This node is not present in Phases 1–3. It is added to the graph in Phase 4.

**Behaviour (Phase 4+):** Activated only when `run_nl_query` sets an error from code execution (not from Gemini API failure). Sends a correction prompt to Gemini including the original question, the generated code that failed, and the error message. Retries code extraction and execution exactly once. If the retry also fails, sets `state["error"]` with both error messages and routes to `handle_error`. On success, clears `state["error"]` and writes the result fields.

---

### `format_response`

**Reads from state:** `summary`, `chart_json`, `table`, `analysis_type`

**Writes to state:** (normalizes and validates existing fields; no new fields)

**LLM call:** No

**External calls:** None

**Behaviour:** Ensures `summary` is a non-empty string (falls back to `"Analysis complete."` if None). Ensures `chart_json` is either a valid JSON string or `None`. Ensures `table` is either a list of dicts or `None`. Truncates `table` to 1000 rows maximum to keep response size manageable. This node always runs after the analysis branch (preset or NL) and before `finalize`.

---

### `handle_error`

**Reads from state:** `error`, `run_id`

**Writes to state:** `status`

**LLM call:** No

**External calls:** None

**Behaviour:** Sets `state["status"] = "failed"`. Logs the error with `run_id` context. Does not modify `state["error"]` — it is preserved for the DB write in `finalize`.

---

### `finalize`

**Reads from state:** `run_id`, `status`, `summary`, `chart_json`, `table`, `error`

**Writes to state:** `status`

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite DB | `UPDATE analyses SET status=?, summary=?, chart_json=?, table_json=?, error_message=? WHERE id=?` | Logs error; does not re-raise (run already complete) |

**Behaviour:** Sets `state["status"] = "completed"` if not already set to `"failed"`. Writes `summary`, `chart_json`, table (JSON-serialized), and `error_message` back to the `analyses` row. This is the terminal node for all paths.

---

## Graph / Flow Topology

```
START
  │
  ▼
parse_upload
  │
  ├──(error set OR unknown analysis_type)────────────────────────────► handle_error ──► finalize ──► END
  │
  ├──(analysis_type in preset types)──► run_preset_analysis
  │                                           │
  │                                           ├──(error)──► handle_error ──► finalize ──► END
  │                                           │
  │                                           └──(no error)──► format_response ──► finalize ──► END
  │
  └──(analysis_type == "nl_query")──► run_nl_query
                                            │
                                            ├──(API error)──► handle_error ──► finalize ──► END
                                            │
                                            │ (Phase 4+: code exec error)
                                            ├──► reflect_nl_result
                                            │         │
                                            │         ├──(retry error)──► handle_error ──► finalize ──► END
                                            │         │
                                            │         └──(success)──► format_response ──► finalize ──► END
                                            │
                                            └──(no error, Phase 1-3)──► format_response ──► finalize ──► END
```

The routing decision (error vs. preset vs. nl_query) is made by the `after_parse_and_route` conditional edge function attached to `parse_upload`. There is no separate routing node.

**Note:** In Phases 1–3, `reflect_nl_result` is not in the graph. The NL query path goes: `run_nl_query` → `format_response` or `handle_error`.

**Conditional edges:**

| Source node | Condition (edge function) | Target |
|-------------|--------------------------|--------|
| `parse_upload` | `after_parse_and_route`: `state.get("error")` is set | `handle_error` |
| `parse_upload` | `after_parse_and_route`: `analysis_type` in preset set | `run_preset_analysis` |
| `parse_upload` | `after_parse_and_route`: `analysis_type == "nl_query"` | `run_nl_query` |
| `parse_upload` | `after_parse_and_route`: unknown `analysis_type` | `handle_error` |
| `run_preset_analysis` | `after_preset`: `state.get("error")` | `handle_error` |
| `run_preset_analysis` | `after_preset`: not `state.get("error")` | `format_response` |
| `run_nl_query` | `after_nl_query`: `state.get("error")` (API failure) | `handle_error` |
| `run_nl_query` | `after_nl_query`: `state.get("code_exec_error")` (Phase 4+) | `reflect_nl_result` |
| `run_nl_query` | `after_nl_query`: no error | `format_response` |
| `reflect_nl_result` | `after_reflect`: `state.get("error")` | `handle_error` |
| `reflect_nl_result` | `after_reflect`: not `state.get("error")` | `format_response` |
| `format_response` | always (fixed edge) | `finalize` |
| `handle_error` | always (fixed edge) | `finalize` |
| `finalize` | always (fixed edge) | `END` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph `DataAnalysisState` TypedDict | All pipeline data: filepath, DataFrame, result fields, error |
| Across runs | SQLite `analyses` table | Analysis results (summary, chart_json, table_json, status, error_message) |
| Upload history | SQLite `uploads` table | Upload metadata (filename, filepath, row/col count, column list) |
| Conversation | Not applicable | This is a request-response agent, not a chat agent; no turn memory needed |

**Context window management:** The NL query prompt includes at most 20 sample rows (as CSV text) to keep the prompt within Gemini's limits. For very wide DataFrames (>30 columns), only the first 30 columns are included in the schema. The DataFrame itself is never serialized into the prompt beyond the sample.

---

## Error Handling & Recovery

**Node-level:** Every node wraps its logic in a try/except. On exception, it sets `state["error"] = str(exc)` and returns the updated state. The conditional edge after each node routes to `handle_error` when `state["error"]` is set.

**Graph-level (`handle_error` node):**
- Reads: `state["error"]`, `state["run_id"]`
- Sets: `state["status"] = "failed"`
- Logs the error with `run_id` and `analysis_type` context to stdout (structlog)
- Routes to `finalize` (not directly to END — finalize always writes the DB record)

**Resume / retry strategy:** No checkpointing (single-user, short-lived runs). A failed run returns an error to the browser immediately. The user can re-submit.

**Partial failure:** All failures are treated as fatal for the current analysis run. The DB record is always written (status=failed + error_message) so the API can return a structured error to the browser. The server process does not crash on analysis failures.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| Run start/end | `analysis_id`, `analysis_type`, duration ms, status | stdout via structlog |
| LLM calls | `run_nl_query` prompt token count (if available from Gemini response metadata), latency | stdout via structlog |
| Node transitions | node name + state keys written | stdout via structlog (DEBUG level) |
| Errors | error message, node name, `analysis_id` | stdout via structlog (ERROR level) |

---

## Concurrency Model

- **Run isolation:** Analyses run synchronously within a single FastAPI request. No concurrency between analyses — FastAPI's default thread-per-request model handles sequential analysis requests. For a single-user local tool, this is sufficient.
- **Parallel nodes within a run:** None. The preset and NL branches are mutually exclusive; no parallel node execution is used.
- **Checkpointing:** None. LangGraph's `SqliteSaver` is not used — runs are short-lived and the server is single-user.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import DataAnalysisState
from graph.nodes import (
    parse_upload,
    run_preset_analysis,
    run_nl_query,
    format_response,
    handle_error,
    finalize,
)
from graph.edges import after_parse_and_route, after_preset, after_nl_query


def _build_graph() -> StateGraph:
    g = StateGraph(DataAnalysisState)

    # Nodes
    g.add_node("parse_upload", parse_upload)
    g.add_node("run_preset_analysis", run_preset_analysis)
    g.add_node("run_nl_query", run_nl_query)
    g.add_node("format_response", format_response)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    # Entry
    g.set_entry_point("parse_upload")

    # parse_upload → run_preset_analysis | run_nl_query | handle_error
    # after_parse_and_route checks state["error"] first; if no error, routes on analysis_type
    g.add_conditional_edges(
        "parse_upload",
        after_parse_and_route,
        {
            "run_preset_analysis": "run_preset_analysis",
            "run_nl_query": "run_nl_query",
            "handle_error": "handle_error",
        },
    )

    # Preset branch
    g.add_conditional_edges(
        "run_preset_analysis",
        after_preset,
        {"format_response": "format_response", "handle_error": "handle_error"},
    )

    # NL query branch (Phase 1-3: direct to format_response on success)
    g.add_conditional_edges(
        "run_nl_query",
        after_nl_query,
        {"format_response": "format_response", "handle_error": "handle_error"},
    )

    # Convergence
    g.add_edge("format_response", "finalize")
    g.add_edge("handle_error", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# Phase 4+ graph with reflection node added:
# After compiling, rebuild with an additional node and edge:
#   g.add_node("reflect_nl_result", reflect_nl_result)
#   update after_nl_query to route code_exec_error → reflect_nl_result
#   g.add_conditional_edges("reflect_nl_result", after_reflect,
#       {"format_response": "format_response", "handle_error": "handle_error"})


agentic_ai = _build_graph()
```

`after_parse_and_route` in `src/graph/edges.py`:
```python
_PRESET_TYPES = {"summary_stats", "trend_over_time", "top_bottom_n", "correlation"}

def after_parse_and_route(state: DataAnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    analysis_type = state.get("analysis_type", "")
    if analysis_type in _PRESET_TYPES:
        return "run_preset_analysis"
    if analysis_type == "nl_query":
        return "run_nl_query"
    return "handle_error"  # unknown analysis_type
```
