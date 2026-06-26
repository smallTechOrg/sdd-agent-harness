# Agent

> The LangGraph agent for the local data-analyst capability. Implemented in `src/graph/` (skeleton layout: nodes in `src/graph/nodes.py`, edges in `src/graph/edges.py`, assembly in `src/graph/agent.py`, state in `src/graph/state.py`, runner in `src/graph/runner.py`).

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges. |

**Chosen:** **Graph (LangGraph)**, composing **Tool Use** (the local sandbox is the one "tool"), **Prompt Chaining** (generate-code → explain-result are two ordered LLM steps), and **Exception Handling & Recovery** (`handle_error` + a bounded retry in Phase 2). It is a fixed, ordered pipeline with one conditional branch per node (error vs continue), which is exactly what a `StateGraph` expresses cleanly. No multi-agent, no supervisor — a single linear graph suffices and keeps the result auditable.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `generate_code` | Google Gemini | `gemini-2.5-flash` | Code generation from schema + small sample; flash is fast and strong enough for idiomatic pandas. Model configurable via `AGENT_LLM_MODEL`. |
| `explain_result` | Google Gemini | `gemini-2.5-flash` | Render a short plain-English explanation from the small computed result; latency matters more than depth. |
| `profile_csv` / `execute_code` | — (no LLM) | — | Pure local pandas — these touch the full data and must NOT involve the LLM (constraint 1). |

**Fallback behaviour:** On a Gemini API/network/quota error, the node sets `state["error"]` and the graph routes to `handle_error` (run status `failed`, message surfaced to the UI). Phase 2 adds **one** bounded retry of `generate_code` when `execute_code` fails, feeding the execution error back into the prompt. Tests call the real Gemini API with `AGENT_GEMINI_API_KEY` from `.env` — there is no offline stub path on the gated path.

**Prompt strategy:** System/user split via `LLMClient().call_model(prompt, system=...)`.
- `generate_code` system prompt (`src/prompts/generate_code.md`): instructs the model to return ONLY a pandas snippet that assigns the answer to a variable named `result`, using the bound DataFrame `df`; no imports, no prose, no markdown fences. The user message contains the **schema** (columns + dtypes), the **capped sample** (≤20 rows as CSV/markdown), and the **question**. Never the full data.
- `explain_result` system prompt (`src/prompts/explain_result.md`): instructs the model to write a 1–3 sentence plain-English answer grounded in the provided question, code, and the small computed result; no new computation.

---

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `run_sandbox` (`src/analysis/sandbox.py`) | Execute the generated pandas snippet **locally** against the full `df` in a restricted namespace | `code: str`, `df: DataFrame` | `result` value normalized to a JSON-serializable scalar or table (`{columns, rows}`) | None external; pure local compute, bounded by timeout + size caps |

**Tool selection strategy:** Deterministic — the graph always calls `run_sandbox` once on the code `generate_code` produced. The LLM does not choose tools; the pipeline is fixed.

**Tool failure handling:** A sandbox error (AST rejection, exec exception, timeout, missing `result`) is categorized and either (Phase 1) sets `state["error"]` → `handle_error`, or (Phase 2) triggers one retry of `generate_code` with the error fed back, then `handle_error` if it still fails.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                          # set at initialisation (runner)

    # Input (from the trigger)
    csv_text: str                        # raw uploaded CSV text (local only, never sent to LLM)
    question: str                        # the natural-language question
    mode: str                            # "pandas" | "sql" — user's choice (Phase 2+)

    # Pipeline data (populated progressively by nodes)
    schema: list[dict]                   # [{name, dtype}] — profile_csv  (LLM-visible)
    sample_rows: list[dict]              # capped sample rows — profile_csv (LLM-visible)
    row_count: int                       # full row count — profile_csv
    generated_code: str                  # pandas snippet or SQL query — generate_code
    result_table: dict | None            # {columns: [...], rows: [[...]]} or scalar-wrapped — execute_code
    result_scalar: object | None         # scalar result when applicable — execute_code
    truncated: bool                      # result-table truncated flag (Phase 3) — execute_code

    # Output
    answer: str | None                   # short answer line — explain_result
    explanation: str | None              # plain-English explanation — explain_result
    status: str                          # "completed" | "failed" — finalize/handle_error

    # Control
    error: str | None                    # set by any node on fatal failure
    retry_count: int                     # bounded retries of generate_code (Phase 3)
```

> Extends the skeleton `AgentState` (`run_id`, `input_text`, `output_text`, `error`). `input_text`/`output_text` are no longer used by the analyst path; the analyst fields above replace them. The DB still stores a compact summary in `output_text` for backward compatibility (the answer + explanation), plus dedicated columns for `generated_code` and `result_table` (see [`data.md`](data.md)).

---

## Nodes / Steps

### `profile_csv`
**Reads from state:** `csv_text`, `question`
**Writes to state:** `schema`, `sample_rows`, `row_count`, full `df` (held in a module-local/state-attached object, NOT serialized to the LLM), or `error`
**LLM call:** No.
**External calls:** None (local pandas only).
**Behaviour:** Parse `csv_text` into a DataFrame via `pandas.read_csv`. Reject (set `error`) if it is empty, unparseable, exceeds `AGENT_MAX_UPLOAD_BYTES`, or exceeds `AGENT_MAX_ROWS`. Build `schema` (column name + inferred dtype per column), a `sample_rows` capped at `AGENT_SAMPLE_ROWS` (default 15, hard cap 20), and `row_count`. The full DataFrame is retained for `execute_code` but never enters any prompt.

### `generate_code`
**Reads from state:** `schema`, `sample_rows`, `question`, `row_count`, `mode`
**Writes to state:** `generated_code`, or `error`

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | Generate a code snippet (pandas or SQL) from schema + sample + question, branched on `mode` | fatal (set `error`) → `handle_error` |

**LLM call:** Yes — Gemini, system prompt chosen by `mode`:
  - **Pandas mode:** system prompt `src/prompts/generate_code.md`, output is a bare pandas snippet assigning to `result`
  - **SQL mode (Phase 2+):** system prompt `src/prompts/generate_sql.md`, output is a bare SQL SELECT query

**Behaviour:** Builds the prompt from schema + capped sample + question (NO full data), calls Gemini with the mode-specific system prompt, strips any markdown fences or SQL comments, stores the snippet in `generated_code`.

### `execute_code`
**Reads from state:** `generated_code`, full `df`, `csv_text`, `mode`
**Writes to state:** `result_table`, `result_scalar`, `truncated`, or `error`
**LLM call:** No.
**External calls:** None — execution runs locally (pandas or SQL).
**Behaviour:** Branched on `mode`:
  - **Pandas:** Statically validates the snippet (AST allow-list: no imports, no dunders, no `os`/`sys`/`open`), executes it in the restricted namespace in `src/analysis/sandbox.py` with `df` bound and a timeout, reads `result`, normalizes to a JSON-serializable scalar or `{columns, rows}` table (capped at `AGENT_MAX_RESULT_ROWS`, setting `truncated`). On rejection/exception/timeout/missing `result`, sets a categorized `error`.
  - **SQL (Phase 2+):** Loads `csv_text` into an in-memory SQLite table, validates the SQL query (SELECT-only, no escapes, AST check), executes it in `src/analysis/sql_executor.py` against the table with a timeout, extracts the result set, normalizes to `{columns, rows}` (capped at `AGENT_MAX_RESULT_ROWS`, setting `truncated`). On validation failure/execution error/timeout, sets a categorized `error`.

### `explain_result`
**Reads from state:** `question`, `generated_code`, `result_table` / `result_scalar`
**Writes to state:** `answer`, `explanation`, or `error`

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | Render a plain-English explanation from the SMALL computed result | fatal (set `error`) → `handle_error` |

**LLM call:** Yes — Gemini, system prompt `explain_result.md`. Receives only the question, the code, and the already-computed small result.
**Behaviour:** Produces a 1–3 sentence answer + explanation grounded in the computed result.

### `finalize`
**Reads from state:** all output fields
**Writes to state:** `status = "completed"`
**Behaviour:** Marks the run completed; the runner persists answer/explanation/code/result to the `RunRow`.

### `handle_error`
**Reads from state:** `error`, `run_id`
**Writes to state:** `status = "failed"`
**Behaviour:** Marks the run failed; the runner persists `error_message`. Terminates the graph.

---

## Graph / Flow Topology

```
START
  │
  ▼
profile_csv ──(error)──► handle_error ──► END
  │
  ▼
generate_code ──(error)──► handle_error
  │
  ▼
execute_code ──(error, Phase 1)────────► handle_error
  │        └──(error, Phase 2 & retry_count<1)──► generate_code   (retry with error fed back)
  ▼
explain_result ──(error)──► handle_error
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `profile_csv` | `state["error"]` set | `handle_error` |
| `profile_csv` | else | `generate_code` |
| `generate_code` | `state["error"]` set | `handle_error` |
| `generate_code` | else | `execute_code` |
| `execute_code` | `error` set AND (Phase 3 and `retry_count < 1`) | `generate_code` (increment `retry_count`) |
| `execute_code` | `error` set (Phase 1–2, or retries exhausted) | `handle_error` |
| `execute_code` | else | `explain_result` |
| `explain_result` | `state["error"]` set | `handle_error` |
| `explain_result` | else | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | schema, sample, full df, generated code, result, answer |
| **Across runs** | SQLite `RunRow` | one row per analysis (question, code, result, answer) — for `GET /runs/{id}`, not reused as context |
| **Conversation** | none | each question is independent (follow-up memory is out of scope) |

**Context window management:** Bounded by construction — only the schema + a ≤20-row sample + the question (and, for explain, the small result) ever enter a prompt. The full dataset never does, so the prompt is small and constant regardless of file size.

---

## Error Handling & Recovery

**Node-level:** Each node wraps its work in try/except (or returns a categorized error from the sandbox); on a fatal problem it sets `state["error"]` and the conditional edge routes to `handle_error`.

**Graph-level (`handle_error` node):**
- Reads: `state.error`, `state.run_id`
- The runner updates the DB: status → `failed`, `error_message` set
- Error is logged with `run_id` context
- Terminates the graph

**Resume / retry strategy:** Phase 3 adds one bounded retry of `generate_code` when `execute_code` fails (the execution error is fed back into the next prompt; `retry_count` caps it at 1), for both pandas and SQL modes. No cross-request resume — each `POST /runs` is a fresh run.

**Partial failure:** There is no graceful-degradation path that returns a wrong number; an unrecoverable failure surfaces a clear error rather than guessing.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One run per `run_id`, node transitions | structlog (stdout) |
| **LLM calls** | model, latency, success/error | structured log |
| **Tool calls** | sandbox: code length, error category, duration | structured log |
| **Run outcome** | status, error if any | SQLite `RunRow` + structured log |

(Structured logging is wired in a later observability phase; Phase 1 uses the existing log level setting.)

---

## Concurrency Model

- **Run isolation:** each `POST /runs` is independent and scoped by `run_id`; runs are stateless across requests. FastAPI handles requests concurrently; the graph holds no shared mutable global beyond the DB session.
- **Parallel nodes within a run:** none — the pipeline is strictly sequential (each step depends on the prior).
- **Checkpointing:** none (no human-in-the-loop, no long-running pause). The graph compiles without a checkpointer.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.nodes import profile_csv, generate_code, execute_code, explain_result, finalize, handle_error
from graph.edges import after_profile, after_generate, after_execute, after_explain

def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("profile_csv", profile_csv)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("explain_result", explain_result)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("profile_csv")
    g.add_conditional_edges("profile_csv", after_profile,
        {"generate_code": "generate_code", "handle_error": "handle_error"})
    g.add_conditional_edges("generate_code", after_generate,
        {"execute_code": "execute_code", "handle_error": "handle_error"})
    g.add_conditional_edges("execute_code", after_execute,
        {"explain_result": "explain_result", "generate_code": "generate_code", "handle_error": "handle_error"})
    g.add_conditional_edges("explain_result", after_explain,
        {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()
```
