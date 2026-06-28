# Capability: NL Query and Answer

## What It Does

Accepts a natural-language question about one or more uploaded files, runs a multi-step ReAct loop (write Python/pandas code → execute in sandbox → inspect result → retry if needed, up to 5 steps), then streams a plain-text answer with an auto-selected interactive Plotly chart and collapsible code steps back to the user in real time.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `question` | `string` (max 2000 chars) | Chat input → `POST /api/query/stream` body | yes |
| `file_ids` | `array[string]` | Request body; each must match an `uploaded_files.id` | yes |
| `session_id` | `string \| null` | Request body | no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Streaming text tokens | SSE `{"type":"token","text":"..."}` events | Browser chat panel (rendered in real time) |
| Code steps | SSE `{"type":"code_step",...}` events (one per iteration) | Browser code accordion (collapsible) |
| Plotly chart | SSE `{"type":"chart","plotly":{...}}` event | Browser inline chart (rendered by `plotly.js`) |
| Cost summary | SSE `{"type":"cost","input_tokens":N,"output_tokens":N,"cost_usd":X}` event | Browser footer |
| `query_runs` row | DB record | SQLite `query_runs` table |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API (`plan_steps`) | Structured chat completion to produce a pandas plan | Retry 3× with back-off; after 3 failures emit `type:"error"` SSE event |
| Sandboxed subprocess | Run generated Python code in a child process (30 s timeout) | On timeout or non-zero exit: count as a failed iteration; if iterations remain, re-plan with stderr as context; otherwise emit `type:"error"` |
| Gemini API (`inspect_result`) | Binary quality judgment on execution output | Retry 3×; on persistent failure treat as `complete:false` (conservative) |
| Gemini API (`synthesize_answer`) | Produce plain-text answer + Plotly JSON | Retry 3×; on failure emit `type:"error"` |
| SQLite | Write `query_runs` row | On failure: log and continue streaming (degraded — no history persistence) |
| Local filesystem (`uploads/`) | Read uploaded file(s) in the subprocess | On missing file: emit `type:"error"` with "File not found: <file_id>" |

## Business Rules

- The agent may execute up to 5 code-execute iterations per query (`max_iterations = 5`). If the result is still unsatisfactory after 5 attempts, `synthesize_answer` is called with the best available result.
- If `iteration == 0` and the question is genuinely ambiguous (e.g., column name collision), `plan_steps` may emit a `type:"clarification"` SSE event instead of proceeding. The user's next message is treated as the reply (sent as a new query).
- The Python code executed in the subprocess must import pandas, may import duckdb, numpy, and plotly. No other third-party imports are permitted. The subprocess has no network access.
- The subprocess output must write its primary result as JSON to stdout. The last line of stdout is parsed as the data result. Any non-JSON output on earlier stdout lines is treated as debug output.
- Chart type selection is the LLM's responsibility in `synthesize_answer`. The LLM chooses from: `bar`, `line`, `scatter`, `histogram`, `heatmap`, `pie`. If no chart is appropriate (e.g., a single scalar answer), `plotly_chart` may be null.
- The Plotly chart JSON must be a valid `plotly.graph_objects.Figure`-compatible dict (i.e., `{"data": [...], "layout": {...}}`). The frontend renders it with `Plotly.react()`.
- Token count and cost are computed from the cumulative totals across all LLM calls within the run (plan + inspect × N + synthesize).
- A `query_runs` row is written with `status='running'` at the start of the SSE stream and updated to `status='completed'` or `status='failed'` when the stream ends.
- The code in the subprocess sees the uploaded files at the paths in `state["data_paths"]`. The subprocess is given these paths as command-line arguments or via an injected `DATA_PATHS` environment variable.

## Success Criteria

- [ ] A question about a 1,250-row CSV returns a streaming answer that begins within 5 seconds of submission.
- [ ] The answer includes a Plotly chart JSON that `plotly.js` can render without errors.
- [ ] The collapsible code accordion shows at least one `ExecutionStep` with non-empty `code` and `stdout`.
- [ ] The cost footer displays `input_tokens > 0` and `cost_usd > 0` after the query completes.
- [ ] If the generated Python code raises an exception on the first attempt, the agent retries with a different approach (verified by `iterations_used >= 2` in `query_runs`).
- [ ] A question that returns a single scalar answer (e.g., "How many rows are there?") returns a correct numeric answer in the text and may omit the chart.
- [ ] If the Gemini API is unavailable (key missing), the SSE stream emits a `type:"error"` event with a clear message and the `query_runs` row is set to `status='failed'`.
- [ ] The answer to a question over a dataset with 500+ rows differs from the answer over just the first 10 rows — proving the agent runs against the full dataset (not a sample).
