# Capability: Query Execution

## What It Does

Executes a validated SQL SELECT statement against the session's stored dataset file(s) using an embedded analytical query engine, writes the event to the audit log, and returns the result set as column names plus rows.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Validated SQL statement | String (SELECT only) | NL Query capability | Yes |
| Session ID | String | Session store reference | Yes |
| Dataset file path(s) | String or array of strings | Session store (resolved by dataset name referenced in SQL) | Yes |
| Source question | String | NL Query capability (for audit log) | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Result set | `{ columns: [string], rows: [[any]] }` | API response to Web UI |
| Audit log entry | Structured record (see Business Rules) | Audit log (append-only file) |
| ConversationTurn (role: assistant) | `{ turn_id, role: "assistant", content: "Returned {N} row(s).", sql, result_summary, timestamp }` | Session store conversation history (appended after successful or failed execution) |

> **Assumed:** The assistant turn `content` is the fixed template string `"Returned {N} row(s)."` where N is the row count from the result set (0 on error). This is not LLM-generated prose.

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem (dataset files) | Read dataset file(s) for query execution | Return HTTP 500 with `dataset_read_error`; write failure to audit log |
| Local filesystem (audit log) | Append audit log entry | Log the write failure to stderr; do not fail the query response — result is still returned to the user |

## Business Rules

- Only SELECT statements may be executed; the capability must not accept or execute DML or DDL. This is a second enforcement gate after NL Query validation.
- The query engine resolves table names in the SQL to the corresponding dataset files in the session store; a table name not matching any uploaded dataset causes a 422 error with `unknown_table`.
- Result sets are capped at 1 000 rows returned to the client; if the query produces more rows, only the first 1 000 are returned and the response includes a `truncated: true` flag with the total row count.
- Every execution attempt — successful or failed — is recorded in the audit log with the following fields: `timestamp` (ISO 8601), `session_id`, `source_question`, `sql`, `row_count` (or `null` on error), `status` (`success` or `error`), `error_message` (or `null`). An `unknown_table` rejection is a pre-execution validation failure and does not produce an audit log entry.
- Query execution timeout: 30 seconds. Queries exceeding this limit are cancelled and return HTTP 504 with a `query_timeout` error; the timeout event is written to the audit log.
- The audit log is append-only; no capability may modify or delete existing entries.

## Success Criteria

- [ ] A valid SELECT query against an uploaded CSV returns a result set with correct column names and data values within 10 seconds.
- [ ] The audit log gains exactly one new entry per query execution attempt, whether or not the query succeeds.
- [ ] A query referencing a table name not present in the session returns HTTP 422 with error code `unknown_table`; no audit entry is written for the SQL (the error is caught before execution).
- [ ] A result set exceeding 1 000 rows is truncated to 1 000 rows; the response body includes `"truncated": true` and the actual total row count.
- [ ] A query that runs longer than 30 seconds is cancelled and returns HTTP 504; the audit log entry for that query has `status: "error"` and a `query_timeout` message.
- [ ] An audit log write failure does not prevent the query result from being returned to the caller.

> **Assumed:** "Table names in the SQL" are matched case-insensitively to the dataset names stored in the session, derived from the uploaded file names (without extension). The tech-architect will confirm the exact name-normalisation rule.
