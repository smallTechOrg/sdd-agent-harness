# Capability: Session and History

> **Phase:** 2. This capability is a labelled stub in Phase 1 and becomes real in Phase 2.

## What It Does

Groups queries and uploaded files into named sessions that persist indefinitely in SQLite. The user can reload the browser and see their previous sessions in the sidebar, click a past query to restore its answer and chart, and continue asking questions within the same session context.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `session_id` | `string \| null` | Request body on each query/upload; browser-managed (stored in `localStorage`) | no |
| `name` | `string` | Optional body field on `POST /api/sessions` | no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `session_id` | `string` (UUID4) | JSON response; stored in browser `localStorage` |
| Session list | `GET /api/sessions` JSON array | Browser sidebar session history panel |
| Query history | `GET /api/sessions/{id}/queries` JSON array | Browser sidebar when a session is expanded |
| Restored answer | Rendered from `query_runs.answer_text` + `plotly_chart_json` | Browser chat panel |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | `INSERT/SELECT sessions` | Return HTTP 500; user stays on current session |
| SQLite | `SELECT query_runs WHERE session_id = ?` | Return HTTP 500 with error message |

## Business Rules

- A session is created automatically on the first query if no `session_id` is provided and none is stored in `localStorage`. The default name is `"Session <YYYY-MM-DD>"`.
- The frontend stores the active `session_id` in `localStorage`. On browser restart, it reads the stored ID and passes it to all subsequent API calls.
- Sessions are never automatically deleted. The user has no delete UI in Phase 2 (deletion is out of scope for Phase 1–3).
- Uploaded files are associated with the session in which they were uploaded (`uploaded_files.session_id`). Files uploaded before Phase 2 (without a session) have `session_id = NULL`.
- `sessions.last_active_at` is updated on every query or upload associated with that session.
- The session history sidebar lists sessions ordered by `last_active_at` descending (most recent first). Each session entry shows its name, date, and query count.
- Clicking a past query in the history list restores the answer text and Plotly chart into the chat panel (read from `query_runs`). It does not re-run the query against the LLM.
- The conversation history within a session is for display only — the agent does not receive prior query results as LLM context (no multi-turn memory). Each query is independent.

> **Assumed:** Conversation memory (feeding prior Q&A turns as LLM context within a session) is deferred to a future phase beyond Phase 3. Each query is independent — the agent sees only the current question and file profiles. This is an explicit scope decision, not a gap.

## Success Criteria

- [ ] After a query with no `session_id`, a new session row exists in `sessions` and the response or the browser `localStorage` contains the new `session_id`.
- [ ] After reloading the browser, the session history sidebar shows the session created in the previous browser session.
- [ ] Clicking a past query in the history sidebar renders its `answer_text` and Plotly chart correctly without making a new Gemini API call.
- [ ] `GET /api/sessions` returns sessions ordered by `last_active_at` descending.
- [ ] `sessions.last_active_at` is updated after each new query within that session.
- [ ] `GET /api/sessions/{id}/queries` returns 404 for a non-existent session ID.
