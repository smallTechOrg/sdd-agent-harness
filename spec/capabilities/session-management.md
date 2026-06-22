# Capability: Session Management

## What It Does

Creates, persists, and restores a server-side session that binds a browser tab to its uploaded datasets and conversation history, so the user can return to an in-progress analysis without re-uploading files or losing chat context.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Session ID cookie | String (UUID) | Browser (sent with every request) | No — absent means create a new session |
| New session request | Implicit (any first request lacking a valid session ID) | Backend API | — |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Session ID | String (UUID) | `Set-Cookie` header on response; stored server-side |
| Session record | Object (see Data Model) | Server-side session store |
| Restored session state | `{ datasets: […], conversation: […] }` | API response on session load |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem (session store) | Read/write session record | Return HTTP 500; do not silently create a new session over a corrupted one |

## Business Rules

- A session is created automatically on the user's first request if no valid session ID cookie is present; the new session ID is returned in `Set-Cookie`.
- Session records are persisted server-side; the cookie contains only the session ID — no session state is stored in the browser.
- Session lifetime: 24 hours from the time of last activity. After expiry the session record and all associated dataset files are eligible for deletion; they are not automatically deleted on expiry (a cleanup job is out of scope for Phase 1).
- A session record holds: session ID, created-at timestamp, last-active-at timestamp, list of dataset metadata objects (ID, name, schema, file path), and ordered conversation history (role + content pairs).
- Conversation history stored in the session is used only for display in the Web UI; it is not sent to the Gemini API (the prompt is always schema + current question only).
- If the session ID cookie refers to a session record that does not exist on the server (expired or deleted), the server creates a new session and returns a new session ID cookie.
- Multiple browser tabs sharing the same session ID share the same session state; concurrent writes are handled with last-write-wins semantics.

## Success Criteria

- [ ] A browser with no session cookie receives a `Set-Cookie` header containing a new UUID session ID on its first request.
- [ ] Closing and reopening the browser (within 24 hours) and presenting the same session ID cookie returns the full dataset list and conversation history that existed before the close.
- [ ] Uploading a dataset in one request and immediately querying in the next request (same session ID) succeeds without re-registering the dataset.
- [ ] A request presenting an unknown session ID (e.g. manually forged or expired) receives a new session ID; it does not see any other user's data.
- [ ] The session record on disk reflects the updated `last-active-at` timestamp after every API request that carries a valid session ID.

> **Assumed:** Sessions are stored as individual JSON files on the local filesystem, one file per session ID, in a dedicated sessions directory. This satisfies the single-server, no-external-database constraint. The tech-architect may substitute an equivalent embedded store.
