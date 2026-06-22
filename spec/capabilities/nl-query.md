# Capability: NL Query

## What It Does

Translates a user's natural-language question into a single, read-only SQL SELECT statement by sending the active session's dataset schema(s) and the question to the Gemini API, then validates the returned SQL before passing it to query execution.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| User question | String | Chat input (via API request body) | Yes |
| Session ID | String (cookie) | Browser session cookie | Yes |
| Dataset schema(s) | Array of `{ dataset_name, columns: [{name, type}] }` | Session store (retrieved by session ID) | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Validated SQL statement | String (SELECT only) | Query Execution capability |
| ConversationTurn (role: user) | `{ turn_id, role: "user", content: question, sql: null, result_summary: null, timestamp }` | Session store conversation history — written before the Gemini API call (pre-condition; not conditional on SQL generation succeeding) |
| ConversationTurn (role: assistant) | `{ turn_id, role: "assistant", content: error message, sql: null, result_summary: null, timestamp }` | Session store — on nl-query failure paths only (see Business Rules) |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | `POST` generate-content with schema + question prompt | Return a structured error to the caller: `{ error: "llm_unavailable", message: "…" }`; do not retry |

## Business Rules

- If the active session contains no datasets, nl-query returns HTTP 422 with error code `no_datasets` immediately, before calling Gemini.
- On `no_datasets`, no ConversationTurn (user or assistant) is written — the request is rejected before any session mutation. No audit log entry is produced.
- The prompt sent to Gemini contains exactly two parts: (1) a fixed system instruction telling it to return only a SQL SELECT statement with no explanation, and (2) the schema(s) of all datasets in the active session plus the user's question. No row data is ever included.
- System instruction length is fixed and minimal; it must not grow with the number of datasets or question length.
- If the Gemini response does not contain a recognisable SQL SELECT statement, the capability returns an error to the caller without calling the Query Engine.
- If the extracted SQL contains any DML or DDL keyword (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`) it is rejected; the capability returns an error without executing anything.
- Each user question is appended as a user ConversationTurn before the Gemini call. On `sql_rejected` (Gemini returned a non-SELECT or unparseable SQL), nl-query writes the assistant ConversationTurn with `content: "Query could not be generated."`, `sql: null`, and `result_summary: null` to the session store. On `llm_unavailable`, nl-query writes the assistant ConversationTurn with `content: "The query service is temporarily unavailable."`, `sql: null`, and `result_summary: null` to the session store. For all other paths the assistant ConversationTurn is written by the Query Execution capability.
- The Gemini API key is read exclusively from the `GEMINI_API_KEY` environment variable; it is never logged, stored, or returned to the client.

## Success Criteria

- [ ] A question referencing a column that exists in the active session's schema produces a syntactically valid SQL SELECT statement.
- [ ] The prompt delivered to Gemini contains the column names and types of every dataset in the session and nothing else from the stored data.
- [ ] A Gemini response that contains an INSERT or DROP statement is rejected; the API returns HTTP 422 with an `sql_rejected` error code.
- [ ] When the Gemini API returns a non-200 response, the capability returns HTTP 502 with an `llm_unavailable` error; the Query Engine is not called.
- [ ] The prompt body sent to Gemini contains the schema strings and question string and does not contain any content from session.conversation.
- [ ] On nl-query failure (`sql_rejected` or `llm_unavailable`), an assistant ConversationTurn is written with the appropriate error content and `sql: null`.
- [ ] Sending a query when the session has no datasets loaded returns HTTP 422 with error code `no_datasets` without calling Gemini.
