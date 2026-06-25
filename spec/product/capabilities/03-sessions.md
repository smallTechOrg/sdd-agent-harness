# Capability 3: Session Management

## Overview

A Session is a named conversation thread on one or more Datasets. The user can create multiple sessions, continue any past session, and delete sessions they no longer need.

A session is the agent's **long-lived context**: it owns a per-session **MCP pool** (one DuckDB-backed MCP server per attached dataset — each dataset is a tool exposing one capability per table — built on the first query and reused thereafter) and **durable memory** (a LangGraph `SqliteSaver` checkpoint keyed by `thread_id = session_id`, so prior Q&A turns carry into later questions). The pool is built lazily, may be idle/LRU-evicted (and transparently rebuilt), and is closed when the session is deleted or the app shuts down. Memory persists across restarts.

## User-Facing Behaviour

- **Home page:** each Dataset card shows session count and last activity; "New Session" button starts immediately.
- **Dataset detail page:** lists all sessions with name, date, query count; "Continue" and "Delete" per session.
- **Session page:** shows the attached datasets as chips (each chip shows the dataset name and its table count) and all Q&A for that session; new questions are appended inline.

## Inputs / Outputs

### Create Session

- **Input:** `POST /datasources/{datasource_id}/sessions` with optional `name` field (a session may attach one or more datasets)
- **Output:** new `Session` record; redirect to `GET /sessions/{session_id}`
- **Default name:** `"Session YYYY-MM-DD HH:MM"` (UTC)

### View Session

- **Input:** `GET /sessions/{session_id}` (optional `?new={query_record_id}`)
- **Output:** HTML with attached-dataset metadata (name + table count per chip) + all QueryRecords for this session newest-first; `?new=` triggers scroll + highlight

### Delete Session

- **Input:** `POST /sessions/{session_id}/delete`
- **Output:** Closes the session's MCP pool (releasing the DuckDB connections of every attached dataset's server), then deletes Session + all QueryRecords + all AgentRuns for those records; redirect to `GET /datasources/{datasource_id}`. (The LangGraph checkpoint for the thread may be left as orphaned rows or cleaned best-effort.)

## Error Cases

| Error | Behaviour |
|-------|-----------|
| Dataset not found | 404 → error.html |
| Session not found | 404 → error.html |
| Delete while a query is in-flight | Best-effort: delete completes, in-flight run eventually writes to a deleted record (no user-visible error in v0.1) |

## Success Criteria

- A new session is created and the user lands on an empty session page
- All past sessions for a Dataset are listed on the Dataset detail page with correct query counts
- Deleting a session removes all its QueryRecords and AgentRuns from SQLite
- The `?new=` parameter scrolls to and highlights the correct Q&A card
