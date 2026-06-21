# Agent Graph

Cross-references (one fact, one place):
- State fields that mirror API payloads → spec/api.md §POST /query
- `audit_log` columns (run_id, action, payload, duration_ms, …) → spec/data-model.md §audit_log (THE home)
- `stub_mode` flag / offline-no-key behaviour → spec/api.md §GET /health + spec/architecture.md
- LLM provider, model id → spec/architecture.md Stack table
- Per-phase acceptance criteria PN-ACn → spec/delivery-plan.md
- Product Success Criteria SC-N → spec/vision.md

---

## Open topology questions

No open topology questions. The graph is a linear three-node pipeline (generate → execute → finalize) with a single shared handle_error terminal. No human-in-the-loop interrupts, no parallel fan-out, no loop back to generate.

---

## State

```python
from typing import TypedDict

class AgentState(TypedDict):
    # Identity
    run_id: str           # UUIDv4 correlation id; mirrors audit_log.run_id (data-model.md §audit_log)
    session_id: str       # caller session id; one run per session at a time (see Concurrency)

    # Input
    question: str         # NL prompt from POST /query request; ≤ 2000 chars
    dataset_ids: list[str]  # uuid4 ids of datasets to query; each maps to a DuckDB table
    column_schemas: list[dict[str, str | bool | None]]  # column_schema rows from dataset registry; for prompt context

    # Pipeline (populated progressively; None until producing node writes it)
    sql: str | None       # the generated SELECT SQL; None until node_generate_sql writes it
    rows: list[dict[str, str | int | float | bool | None]] | None  # query result rows; None until node_execute_sql writes it
    row_count: int | None  # len(rows); None until node_execute_sql writes it
    columns: list[str] | None  # column names in result order; None until node_execute_sql writes it
    chart_spec: dict[str, object] | None  # Plotly spec dict; None if no chartable columns or not yet generated
    table_markdown: str | None  # GFM table of first min(row_count,50) rows; None until node_finalize writes it
    suggestions: list[str]  # follow-up suggestion strings; empty list until Phase 3 node writes it

    # Control
    error: str | None     # set by ANY node on fatal failure; routes to node_handle_error
```

| Field | Group | Type | None until | Set by node | Read by node(s) |
|-------|-------|------|-----------|-------------|-----------------|
| `run_id` | Identity | `str` | n/a (set at graph entry) | (entry init) | all |
| `session_id` | Identity | `str` | n/a (set at graph entry) | (entry init) | all |
| `question` | Input | `str` | n/a (from request) | (entry init) | `node_generate_sql` |
| `dataset_ids` | Input | `list[str]` | n/a (from request) | (entry init) | `node_generate_sql`, `node_execute_sql` |
| `column_schemas` | Input | `list[dict[str, str \| bool \| None]]` | n/a (loaded at entry from SQLite) | (entry init) | `node_generate_sql` |
| `sql` | Pipeline | `str \| None` | `node_generate_sql` writes it | `node_generate_sql` | `node_execute_sql`, `node_finalize`, `node_handle_error` |
| `rows` | Pipeline | `list[dict[str, str \| int \| float \| bool \| None]] \| None` | `node_execute_sql` writes it | `node_execute_sql` | `node_finalize` |
| `row_count` | Pipeline | `int \| None` | `node_execute_sql` writes it | `node_execute_sql` | `node_finalize` |
| `columns` | Pipeline | `list[str] \| None` | `node_execute_sql` writes it | `node_execute_sql` | `node_finalize` |
| `chart_spec` | Pipeline | `dict[str, object] \| None` | `node_finalize` writes it | `node_finalize` | (response assembly) |
| `table_markdown` | Pipeline | `str \| None` | `node_finalize` writes it | `node_finalize` | (response assembly) |
| `suggestions` | Pipeline | `list[str]` | init `[]` | `node_finalize` (Phase 3: `node_suggest`) | (response assembly) |
| `error` | Control | `str \| None` | init `None` | any node on fatal failure | `node_handle_error` |

---

## Nodes

### `node_generate_sql`

| Aspect | Value |
|--------|-------|
| Reads | `question`, `dataset_ids`, `column_schemas`, `run_id`, `session_id` |
| Writes | `sql`, `error` |
| Serves | SC-CORE "WHEN a NL question is submitted, API SHALL return rows length >= 1 and non-empty sql" · P2-AC1 |

**I/O & Guard**

| Aspect | Value |
|--------|-------|
| Prompt / data inputs | `question` (the NL prompt), `column_schemas` (column names + dtypes from each dataset), `dataset_ids` (mapped to DuckDB table names `dataset_<id>`) |
| Output field written | `sql` |
| Guard (predicate) | `sql is not None and sql.strip().upper().startswith("SELECT") and ";" not in sql.rstrip(";") and len(sql.strip()) > 6` |
| On guard fail | fatal: set `state.error = "BAD_SQL: generated SQL is not a valid read-only SELECT"` |

**External calls**

| System | Operation | Timeout | Retries (count, base_ms, cap_ms, jitter) | Idempotent? | Stub fallback | On failure |
|--------|-----------|---------|------------------------------------------|-------------|---------------|------------|
| Google Gemini API | NL→SQL completion (gemini-2.5-flash; context caching on system prompt; see architecture.md Stack) | 30s | (2, 250, 4000, yes) | yes (same prompt → same SQL) | `sql="SELECT product, SUM(revenue) AS total_revenue FROM dataset_stub GROUP BY product ORDER BY total_revenue DESC LIMIT 5"` | fatal: set state.error = "LLM_ERROR: <exc message>" |

**Behaviour:** Sends the question and column schemas to gemini-2.5-flash as a structured prompt requesting a single read-only SELECT SQL statement, then validates the guard predicate and writes `sql` to state.

---

### `node_execute_sql`

| Aspect | Value |
|--------|-------|
| Reads | `sql`, `dataset_ids`, `run_id`, `session_id` |
| Writes | `rows`, `row_count`, `columns`, `error` |
| Serves | SC-CORE · SC-6 "WHEN SQL executes, audit_log row written with duration_ms >= 0" · P2-AC2 |

**I/O & Guard**

| Aspect | Value |
|--------|-------|
| Prompt / data inputs | `sql` (the SELECT to execute), `dataset_ids` (to confirm tables exist in DuckDB) |
| Output field written | `rows` (and also `row_count`, `columns` as co-outputs of the same operation) |
| Guard (predicate) | `rows is not None and isinstance(rows, list) and all(isinstance(r, dict) for r in rows) and row_count == len(rows)` |
| On guard fail | fatal: set `state.error = "QUERY_ERROR: result shape invalid"` |

**External calls**

| System | Operation | Timeout | Retries (count, base_ms, cap_ms, jitter) | Idempotent? | Stub fallback | On failure |
|--------|-----------|---------|------------------------------------------|-------------|---------------|------------|
| DuckDB `./data/app.duckdb` | Execute SELECT query (`duckdb.connect().execute(sql).fetchall()`) | 5s | (3, 100, 2000, no) | yes (read-only SELECT) | `rows=[{"product": "Widget A", "total_revenue": 5000.0}, {"product": "Widget B", "total_revenue": 4200.0}, {"product": "Widget C", "total_revenue": 3800.0}, {"product": "Widget D", "total_revenue": 3100.0}, {"product": "Widget E", "total_revenue": 2900.0}], row_count=5, columns=["product","total_revenue"]` | fatal: set state.error = "QUERY_ERROR: <duckdb exc message>" |

**Behaviour:** Executes the guard-validated SELECT SQL against DuckDB, caps results at `DAA_MAX_RESULT_ROWS`, writes rows/row_count/columns to state, and appends an `audit_log` row with `action='sql'`, the SQL as payload, and measured `duration_ms`.

---

### `node_finalize`

| Aspect | Value |
|--------|-------|
| Reads | `sql`, `rows`, `row_count`, `columns`, `suggestions`, `run_id`, `session_id` |
| Writes | `chart_spec`, `table_markdown` (and assembles the final response) |
| Serves | SC-CORE · SC-UX · SC-6 · P1-AC3 · P2-AC1 |

**I/O & Guard**

| Aspect | Value |
|--------|-------|
| Prompt / data inputs | `rows`, `columns` (to generate chart_spec), `rows` sliced to 50 (for table_markdown) |
| Output field written | `chart_spec` |
| Guard (predicate) | `table_markdown is not None and isinstance(table_markdown, str) and (chart_spec is None or (isinstance(chart_spec, dict) and "data" in chart_spec and "layout" in chart_spec))` |
| On guard fail | partial: write `chart_spec=None` (chart rendering is optional; table is sufficient) |

**External calls**

| System | Operation | Timeout | Retries (count, base_ms, cap_ms, jitter) | Idempotent? | Stub fallback | On failure |
|--------|-----------|---------|------------------------------------------|-------------|---------------|------------|
| none | in-process chart type selection and GFM table generation | n/a | no retry | yes | `chart_spec={"data":[{"type":"bar","x":["Widget A","Widget B","Widget C","Widget D","Widget E"],"y":[5000.0,4200.0,3800.0,3100.0,2900.0]}],"layout":{"title":"Results","xaxis":{"title":"product"},"yaxis":{"title":"total_revenue"}}}` | partial: write chart_spec=None |

**Behaviour:** Selects chart type by data shape (line for datetime column, bar for categorical+numeric, scatter for two numeric columns), builds a Plotly spec dict, serialises the first 50 rows as a GFM Markdown table, writes an `audit_log` row with `action='llm'` (for the upstream LLM call duration), appends conversation_message rows (user + assistant), and updates query_run.status to 'done'.

---

### `node_suggest` (→ Phase 3)

| Aspect | Value |
|--------|-------|
| Reads | `question`, `columns`, `rows`, `sql`, `run_id`, `session_id` |
| Writes | `suggestions`, `error` |
| Serves | SC-8 "WHERE Phase 3 analyst-workflow features are active, response SHALL include ≥ 2 follow-up suggestions" · P3-AC3 |

**I/O & Guard**

| Aspect | Value |
|--------|-------|
| Prompt / data inputs | `question`, `columns`, `sql`, sample from `rows` (first 5 rows) |
| Output field written | `suggestions` |
| Guard (predicate) | `isinstance(suggestions, list) and len(suggestions) >= 2 and all(isinstance(s, str) and len(s) > 0 for s in suggestions)` |
| On guard fail | partial: write `suggestions=["Explore further", "Compare across groups"]` (generic fallbacks, not fatal) |

**External calls**

| System | Operation | Timeout | Retries (count, base_ms, cap_ms, jitter) | Idempotent? | Stub fallback | On failure |
|--------|-----------|---------|------------------------------------------|-------------|---------------|------------|
| Google Gemini API | Follow-up suggestion generation (gemini-2.5-flash; see architecture.md Stack) | 15s | (1, 250, 2000, yes) | yes | `suggestions=["Break down by category", "Show revenue trend over time"]` | partial: write suggestions=["Explore further", "Compare across groups"] |

**Behaviour:** Sends the question, column names, SQL, and 5-row sample to gemini-2.5-flash requesting ≥ 2 follow-up question suggestions that each reference a column name from the result; validates guard; writes suggestions to state.

---

## Edge Topology

```
START
  │
  ▼
node_generate_sql ──(state["error"] is not None)──► node_handle_error ──► END
  │ state["error"] is None
  ▼
node_execute_sql ──(state["error"] is not None)──► node_handle_error
  │ state["error"] is None
  ▼
[Phase 3 only: node_suggest] ──(state["error"] is not None)──► node_handle_error
  │ state["error"] is None (or Phase 1–2: direct)
  ▼
node_finalize ──► END
```

| After node | Condition (predicate over state) | Goes to |
|------------|----------------------------------|---------|
| `node_generate_sql` | `state.get("error") is not None` | `node_handle_error` |
| `node_generate_sql` | `state.get("error") is None` | `node_execute_sql` |
| `node_execute_sql` | `state.get("error") is not None` | `node_handle_error` |
| `node_execute_sql` | `state.get("error") is None` | `node_suggest` (Phase 3) or `node_finalize` (Phase 1–2) |
| `node_suggest` | `state.get("error") is not None` | `node_handle_error` |
| `node_suggest` | `state.get("error") is None` | `node_finalize` |
| `node_finalize` | always | END |
| `node_handle_error` | always | END |

---

## Error & Finalize Nodes

### `node_handle_error`

| Aspect | Value |
|--------|-------|
| Reads | `error`, `run_id`, `session_id`, `sql` (may be None) |
| Writes | nothing in state (terminal side-effect only) |
| Audit write | `audit_log` row: `action='error'`, `payload=state["error"]` (≤ 32768 chars), `duration_ms=<elapsed monotonic ms since run start>`, `model=None`, `input_tokens=None`, `output_tokens=None` (columns per data-model.md §audit_log) |
| Terminates | routes unconditionally to END |

**Behaviour:** Records the failure with `run_id` as `audit_log.run_id`, sets `query_run.status='error'` and `query_run.error_code` from the first word of `state["error"]` (e.g. "BAD_SQL"), routes to END; MUST NEVER raise (last line of defence). The API layer reads `state["error"]` and maps it to the canonical error envelope (api.md §POST /query Error matrix).

### `node_finalize`

| Aspect | Value |
|--------|-------|
| Reads | `sql`, `rows`, `row_count`, `columns`, `chart_spec`, `table_markdown`, `suggestions`, `run_id`, `session_id` |
| Writes | `chart_spec`, `table_markdown`; side-effects: audit_log, conversation_message, query_run update |
| Audit write | `audit_log` row: `action='llm'`, `payload=<NL question>`, `duration_ms=<total run elapsed ms>`, `model=DAA_LLM_MODEL`, `input_tokens=<from Gemini response>`, `output_tokens=<from Gemini response>` (columns per data-model.md §audit_log) |
| Terminates | routes unconditionally to END |

**Response shape:**

```
query_run_id: str            # the query_run.id for this run
sql: str                     # the executed read-only SQL; non-empty on success
columns: list[str]           # column names in result order
rows: list[dict]             # query result rows; >= 0 items
row_count: int               # len(rows)
chart_spec: dict | None      # Plotly spec dict; None if no chartable columns
suggestions: list[str]       # follow-up suggestions; [] in Phase 1–2
table_markdown: str          # GFM table of first min(row_count,50) rows
stub_mode: bool              # mirrors DAA_LLM_PROVIDER==stub
```

**Behaviour:** Closes a successful run — writes the `audit_log` row for the LLM call with `duration_ms`, appends two `conversation_message` rows (role='user' for question, role='assistant' for table_markdown), sets `query_run.status='done'`, assembles the final response object from pipeline state fields, routes to END.

### Acceptance criteria (EARS — finalize/error are observable via audit log)

| # | EARS statement | Acceptance test (command / pytest node / assertion) | Serves |
|---|---------------|------------------------------------------------------|--------|
| AG-AC1 | `WHEN a run completes successfully, node_finalize SHALL write exactly 1 audit_log row with action='llm' and duration_ms >= 0 AND return a response containing every field in the Response-shape block above.` | `pytest tests/test_graph.py::test_finalize_writes_audit` — `assert audit_count_delta == 1 and row.action == "llm" and row.duration_ms >= 0 and set(response.keys()) == {"query_run_id","sql","columns","rows","row_count","chart_spec","suggestions","table_markdown","stub_mode"}` | SC-6 |
| AG-AC2 | `IF any node sets state.error, THEN node_handle_error SHALL write 1 audit_log row with action='error' and a non-empty payload, and the graph SHALL route to END without raising.` | `pytest tests/test_graph.py::test_error_path` — inject a guard failure; `assert audit_rows_with_action_error == 1 and row.payload != "" and no exception escapes run()` | SC-FAIL |
| AG-AC3 | `WHILE stub_mode is true (no API key), the agent SHALL complete a run end-to-end, node_generate_sql SHALL write sql equal to the declared stub value, and node_finalize SHALL write its audit_log row.` | `DAA_LLM_PROVIDER=stub pytest tests/test_graph.py::test_stub_run` — `assert state["sql"].startswith("SELECT") and len(state["rows"]) >= 1 and audit_llm_row_count == 1` | SC-STUB |
| AG-AC4 | `IF a run is already active for a session, THEN POST /query SHALL return HTTP 409 with error.code == "RUN_ACTIVE", not start a second run.` | `pytest tests/test_graph.py::test_concurrent_run_rejected` — fire two concurrent POST /query requests for the same session; `assert second_response.status_code == 409 and second_response.json()["error"]["code"] == "RUN_ACTIVE"` | SC-FAIL |
| AG-AC5 | `WHERE checkpointing is enabled, WHEN a run resumes from a checkpoint, the graph SHALL read the prior step's state and not re-execute completed nodes.` | N/A this phase — no checkpointer in Phase 1–2; Phase 3 revisit if multi-step plans introduced | SC-CORE |

---

## Graph Assembly

```python
# NOTE: the real src/agent/graph.py MUST be <= 60 lines (assembly only; node bodies in src/agent/nodes/).
from typing import Literal

class AgentRunner:
    """Hand-rolled linear node runner (no LangGraph dependency)."""

    async def run(self, initial_state: AgentState) -> AgentState:
        state = initial_state

        # Phase 1-2: generate → execute → finalize
        # Phase 3: generate → execute → suggest → finalize
        nodes_phase_1_2 = [node_generate_sql, node_execute_sql, node_finalize]
        nodes_phase_3   = [node_generate_sql, node_execute_sql, node_suggest, node_finalize]

        import os
        nodes = nodes_phase_3 if os.getenv("DAA_PHASE", "2") == "3" else nodes_phase_1_2

        for node_fn in nodes:
            state = await node_fn(state)
            if state.get("error"):
                state = await node_handle_error(state)
                return state

        return state
```

---

## Concurrency & Checkpointing

| Aspect | Decision | Trigger to revisit |
|--------|----------|--------------------|
| Concurrency | One run per session at a time; POST /query returns 409 with `error.code="RUN_ACTIVE"` while a run is active (see api.md §POST /query Error matrix) | If run latency consistently > 30 s or if a batch-mode feature is added |
| Checkpointing | None (sub-second single pass in stub mode; ≤ 30 s in live mode; no multi-step plan, no HITL interrupt in Phase 1–3) | When multi-step planning or human-in-the-loop interrupt lands in a future phase |
| State persistence between steps | In-memory only (the `AgentState` dict lives for the duration of one HTTP request) | When checkpointing is introduced |

| Phase | Concurrency model | Checkpointing | Notes |
|-------|-------------------|---------------|-------|
| Phase 1 | One run per session (409 while active) | None (stub agent, sub-second) | stub_mode banner visible; all nodes return deterministic canned values |
| Phase 2 | One run per session (409 while active) | None (linear single-pass ≤ 30 s) | live Gemini call; node_generate_sql + node_execute_sql real |
| Phase 3 | One run per session (409 while active) | None (linear 4-node pass ≤ 45 s) | adds node_suggest; revisit checkpointing if latency climbs |

### Acceptance criteria (EARS)

| # | EARS statement | Acceptance test | Serves |
|---|---------------|-----------------|--------|
| AG-AC4 | `IF a run is already active for a session, THEN POST /query SHALL return HTTP 409 with error.code == "RUN_ACTIVE", not start a second run.` | `pytest tests/test_graph.py::test_concurrent_run_rejected` — fire two concurrent POSTs for same session; `assert second.status_code == 409 and second.json()["error"]["code"] == "RUN_ACTIVE"` | SC-FAIL |
| AG-AC5 | `WHERE checkpointing is enabled, WHEN a run resumes from a checkpoint, the graph SHALL read the prior step's state and not re-execute completed nodes.` | N/A Phase 1–3 — no checkpointer; note "N/A this phase — no checkpointer" | SC-CORE |
