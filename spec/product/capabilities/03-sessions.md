# Capability 3: Session Management

## Overview

A Session is a named conversation thread over one or more **MCP servers**. The user can create multiple
sessions, continue any past session, and delete sessions they no longer need.

A session is the agent's **long-lived context**: it owns a per-session **MCP pool** (one DuckDB-backed
in-process server per attached MCP-server entity, built on the first query and reused) and **durable
memory** (a LangGraph `SqliteSaver` checkpoint keyed by `thread_id = session_id`). The pool is built
lazily, may be idle/LRU-evicted (and transparently rebuilt), and is closed when the session is deleted or
the app shuts down. Memory persists across restarts.

## User-Facing Behaviour

- **Home page:** the right column lists sessions (name, date, server chips, query count) with New/Open/
  Delete; the left column lists MCP servers.
- **Session page:** shows the attached MCP servers as chips (each chip: server name + table count) and all
  Q&A for that session; new questions append inline.

## Inputs / Outputs

### Create Session

- **Input:** `POST /sessions` — optional `name` + `database_ids` (≥1 required; a session may attach many)
- **Output:** new `Session` record + `SessionDatabase` links; redirect to `GET /sessions/{session_id}`
- **Default name:** `"Session YYYY-MM-DD HH:MM"` (UTC)

### View Session

- **Input:** `GET /sessions/{session_id}` (optional `?new={query_record_id}`)
- **Output:** HTML with attached-server chips (name + table count) + all QueryRecords newest-first; `?new=`
  scrolls + highlights

### Delete Session

- **Input:** `POST /sessions/{session_id}/delete`
- **Output:** closes the session's MCP pool (releasing each attached server's DuckDB connections), then
  deletes Session + its QueryRecords + AgentRuns; redirect to `GET /`. (The LangGraph checkpoint for the
  thread may be left orphaned or cleaned best-effort.)

## Error Cases

| Error | Behaviour |
|-------|-----------|
| Server not found | 404 → structured `{code, message}` error |
| Session not found | 404 → structured `{code, message}` error |
| Delete while a query is in-flight | Best-effort: delete completes; the in-flight run eventually writes to a deleted record (no user-visible error in v0.1) |

## Success Criteria

- A new session is created and the user lands on an empty session page.
- Sessions list with correct attached-server chips and query counts.
- Deleting a session removes all its QueryRecords and AgentRuns and closes the pool (lock-safe).
- The `?new=` parameter scrolls to and highlights the correct Q&A card.
