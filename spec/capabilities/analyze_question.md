# Capability: Analyze Question

> **Status: ACTIVE — Phase 1 core path.** The single capability that proves the idea.

## What It Does
Takes a plain-English question about an uploaded dataset, computes the answer locally in DuckDB, and returns a plain-English answer with the exact DuckDB SQL that produced every figure — sending Gemini only schema and aggregate result rows, never raw data.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | path param (`POST /datasets/{id}/ask`) | yes |
| question | str | request body | yes |
| schema | list[{name,type}] | `Dataset.schema_json` (loaded by runner) | yes |
| dataset_path | str | `Dataset.duckdb_path` (loaded by runner) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | str | API response `data.answer` |
| sql | str | API response `data.sql` (the exact DuckDB query) |
| result | list[dict] | API response `data.result` (aggregate rows) |
| flagged | bool | API response `data.flagged` (best-guess badge) |
| Run row | DB | `runs` table — question, sql, result_json, status, tokens (audit trail) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini `gemini-3.1-pro` | generate DuckDB SQL from question + schema; phrase answer from result | transient → retry/backoff; persistent → run `failed`, surfaced error, no fabricated number |
| DuckDB (local) | execute generated SQL against the dataset file | DuckDB error → retry-on-SQL-error loop (error fed back to model, bounded by `max_sql_retries`); exhausted → flagged failure |

## Business Rules
- **Privacy boundary:** only schema + aggregate result rows are sent to Gemini. No raw source row ever enters a prompt.
- **DuckDB dialect:** all generated SQL is DuckDB SQL; date/time logic uses DuckDB functions, never SQLite `julianday()` etc.
- **Retry-on-SQL-error:** a DuckDB execution error is fed back verbatim so the model corrects the query (up to `max_sql_retries`, default 3).
- **Never guess silently:** an ambiguous question yields a clearly-`flagged` best-guess; a failure is surfaced, never replaced by an invented figure.
- **Reproducibility:** the returned `sql` run against the dataset reproduces the figure in `answer`.

## Success Criteria
- [ ] Upload a CSV, ask "what is the total of column X", get an answer containing the correct sum and the exact DuckDB SQL.
- [ ] The returned `sql`, executed against the dataset, yields the same number as stated in `answer`.
- [ ] An automated test inspects the prompt sent to Gemini and asserts it contains the schema but **no raw data rows**.
- [ ] When the model first emits invalid SQL (forced in a test), the DuckDB error is fed back and a corrected query succeeds — or, if retries exhaust, the response is `status:"failed"` with no fabricated number.
- [ ] A `Run` row is persisted with question, sql, result, and status.
- [ ] The integration test runs against the **real Gemini API** via `.env`.
