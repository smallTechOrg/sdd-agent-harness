# Capability: Preset and NL Query Analysis

## What It Does

Runs a preset pandas computation or a Gemini-powered free-text query on a previously uploaded file, returning a plain-English summary, an optional Plotly chart, and an optional data table.

## Inputs

| Input | Type | Source | Required |
|-------|------|---------|----------|
| upload_id | UUID string | Client | Yes |
| analysis_type | string | Client | Yes |
| params | object | Client | Conditional on type |
| question | string | Client | Only for nl_query |

`analysis_type` must be one of: `summary_stats`, `trend_over_time`, `top_bottom_n`, `correlation`, `nl_query`.

Params by type:
- `summary_stats` — no params
- `trend_over_time` — `{ "date_col": str, "value_col": str }`
- `top_bottom_n` — `{ "col": str, "n": int, "direction": "top"|"bottom" }` (n must be 1 to 100)
- `correlation` — `{ "col_a": str, "col_b": str }` (both must be numeric columns)
- `nl_query` — no params; question goes in top-level `question` field

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| analysis_id | UUID string | API response + analyses table |
| status | "completed" or "failed" | API response + analyses table |
| summary | string or null | API response; plain-English card in UI |
| chart_json | Plotly JSON string or null | API response; rendered by plotly.js in browser |
| table | list of dicts or null (max 1000 rows) | API response; paginated table in UI |
| error_message | string or null | API response; present only on failure |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Read uploaded file into pandas DataFrame | Set error in state; finalize with status=failed |
| SQLite DB (read) | SELECT filepath FROM uploads WHERE id=upload_id | Set error in state; finalize with status=failed |
| SQLite DB (write) | UPDATE analyses SET result WHERE id=analysis_id | Log error; still return in-memory result |
| Gemini API | nl_query only — generate pandas code from prompt | Set error in state; finalize with status=failed |

## Business Rules

**summary_stats:** Compute count, mean, median, min, max, and std per numeric column; top-10 value counts per non-numeric column. Return a Plotly bar chart (distribution of the first numeric column in 20 buckets), a summary paragraph, and a stats table with one row per column. Zero LLM calls on this path.

**trend_over_time:** Parse date_col via pd.to_datetime. Group by date (daily if span exceeds 90 days, raw dates otherwise). Plotly line chart of value_col. Summary includes date range, start and end values, and overall trend direction. Fail with a user-readable error if date_col cannot be parsed. Zero LLM calls on this path.

**top_bottom_n:** Sort by col descending (top) or ascending (bottom); take n rows. Plotly horizontal bar chart. Summary string. All columns in table. Reject n outside 1 to 100 with status=failed. Zero LLM calls on this path.

**correlation:** Drop NaN rows for col_a and col_b. Compute Pearson r via df[col_a].corr(df[col_b]). Plotly scatter chart. Summary: "Pearson r = {value}. Interpretation: strong/moderate/weak positive/negative correlation." Up to 100 sample rows in table. Fail with a user-readable error if either column is non-numeric. Zero LLM calls on this path.

**nl_query flow:**
1. Build Gemini prompt: system prompt from src/prompts/nl_query.md + DataFrame schema (column names and dtypes) + up to 20 sample rows as CSV text + user question.
2. Call Gemini. Extract the first fenced Python code block. If none found, return status=failed with message "Could not extract code from model response."
3. Execute extracted code in restricted namespace containing only df (the DataFrame) and pd (pandas). No other imports permitted. Execution timeout: 10 seconds (Phase 4+).
4. Convert result: DataFrame to table (up to 100 rows) plus shape summary; scalar to summary sentence; Plotly figure to chart_json; pandas Series treated as single-column DataFrame.
5. If code execution raises an error: route to reflect_nl_result (Phase 4+) for one correction retry; if retry also fails return status=failed.
6. Only question text, schema, and up to 20 sample rows are sent to Gemini. Full file bytes never leave the machine.

**Preset-path LLM constraint:** The LangGraph routing ensures no preset type ever reaches run_nl_query. LLMClient is never instantiated on any preset path — enforced by graph structure, verifiable by test assertion.

## Success Criteria

- [ ] summary_stats on a CSV with at least 5 numeric columns returns status=completed, a non-empty summary string, a valid Plotly JSON string in chart_json, and a non-empty table — with zero Gemini API calls confirmed by test assertion.
- [ ] trend_over_time with a parseable date column and a numeric value column returns a Plotly line chart JSON and a summary string that includes the date range.
- [ ] top_bottom_n with n=5 and direction=top returns exactly 5 rows in table sorted descending by the target column.
- [ ] correlation on two numeric columns returns a summary string containing a Pearson r value and a scatter chart in chart_json.
- [ ] nl_query on a 500-row CSV calls Gemini exactly once and returns status=completed with a summary that reflects full-data computation — verified by asserting the answer differs from a computation run on only the first 10 rows.
- [ ] A request with a nonexistent upload_id returns status=failed with a non-empty error_message.
- [ ] Preset tests assert zero Gemini API calls by monkeypatching LLMClient and asserting it is never instantiated during the test.
