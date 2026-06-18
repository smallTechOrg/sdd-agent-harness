# API

## API Style

Async **FastAPI** REST API with **SSE** streaming (the default trigger for this release; a Next.js chat
UI is **deferred to a later phase** — see [`01-vision.md`](01-vision.md) § Future Phases). Every route
returns the standard JSON envelope — `ok(data)` on success or `api_error(code, message, status)` on
failure ([`../engineering/code-style.md`](../engineering/code-style.md) § Errors are JSON). Errors are
never an HTML page; a client renders them.

**Interaction model:** **multi-turn chat.** A conversation is bound to one dataset; each question is a
turn whose answer streams back over **Server-Sent Events (SSE)**.

Envelope shape:

```json
// success
{ "ok": true, "data": { /* ... */ } }
// error
{ "ok": false, "error": { "code": "CSV_PARSE_ERROR", "message": "..." } }
```

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Create a named, empty dataset.

**Request:**
```json
{ "name": "string — dataset name, e.g. \"Q1 Sales\"" }
```

**Response:** `201` —
```json
{ "ok": true, "data": { "id": "uuid", "name": "string", "created_at": "datetime", "files": [] } }
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 422 | missing/empty name (Pydantic validation) |

---

### `POST /datasets/{dataset_id}/files`

**Purpose:** Upload one or more CSV files into a dataset; parse, infer schema, load into DuckDB.

**Request:** `multipart/form-data` with one or more `files` parts (CSV).

**Response:** `201` — each file's inferred columns are under `schema_columns`:
```json
{ "ok": true, "data": {
  "dataset_id": "uuid",
  "files": [
    { "id": "uuid", "dataset_id": "uuid", "filename": "sales_2024.csv", "duckdb_table": "ds_...",
      "row_count": 1200,
      "schema_columns": [ { "name": "region", "type": "object" }, { "name": "sales", "type": "int64" } ],
      "created_at": "datetime" }
  ]
} }
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 413 | file exceeds the upload size limit (`FILE_TOO_LARGE`) |
| 422 | empty/unparseable CSV (`BAD_CSV`) |
| 404 | dataset not found (`NOT_FOUND`) |

---

### `GET /datasets`

**Purpose:** List datasets (with their files) for the dataset picker, newest first.

**Response:** `data` is an array of dataset objects (same shape as `GET /datasets/{id}`):
```json
{ "ok": true, "data": [
  { "id": "uuid", "name": "Q1 Sales", "created_at": "datetime",
    "files": [ { "id": "uuid", "filename": "sales_2024.csv", "row_count": 1200,
                 "schema_columns": [ { "name": "region", "type": "object" } ] } ] }
] }
```

---

### `GET /datasets/{dataset_id}`

**Purpose:** Get a dataset with its files and inferred schemas (shown before/while chatting).

**Response:**
```json
{ "ok": true, "data": {
  "id": "uuid", "name": "Q1 Sales", "created_at": "datetime",
  "files": [ { "id": "uuid", "filename": "sales_2024.csv", "row_count": 1200,
              "schema_columns": [ { "name": "region", "type": "object" } ] } ]
} }
```

**Error cases:** 404 (`NOT_FOUND`).

---

### `DELETE /datasets/{dataset_id}`

**Purpose:** Delete a dataset (and its files, conversations, runs) and drop its DuckDB data —
releasing the session-scoped engine ([`../engineering/patterns/react-agent.md`](../engineering/patterns/react-agent.md)
§ Resource lifecycle).

**Response:** `{ "ok": true, "data": { "deleted": "uuid" } }`  ·  **Error:** 404 (`NOT_FOUND`).

---

### `POST /conversations`

**Purpose:** Start a conversation bound to a dataset.

**Request:**
```json
{ "dataset_id": "uuid" }
```

**Response:** `201` —
```json
{ "ok": true, "data": { "id": "uuid", "dataset_id": "uuid", "title": null, "created_at": "datetime" } }
```

**Error cases:** 404 (dataset `NOT_FOUND`).

---

### `POST /conversations/{conversation_id}/query`  (SSE)

**Purpose:** Ask a question (first or follow-up) in a conversation. Runs the ReAct agent and **streams**
the live trace and final answer. This is the multi-turn NL-query entry point.

**Request:**
```json
{ "question": "string — e.g. \"total sales by region\"" }
```

**Response:** `text/event-stream`. Event payloads (each `data:` line is JSON):
| Event | Payload |
|-------|---------|
| `step` | the full `action_history` entry: `{ "description", "action", "result", "is_error" }` — one per executed action (the live trace; `description` is plain-English) |
| `answer` | the assistant message: `{ "id", "conversation_id", "run_id", "role", "content", "result_table": { "columns", "rows" }, "trace", "created_at" }` |
| `done` | `{ "run_id", "status", "tokens_input", "tokens_output", "estimated_cost_usd", "early_exit_reason" }` |
| `error` | `{ "code": "RUN_FAILED" \| "DATASET_NOT_LOADED", "message": "…" }` (stream then closes) |

**Error cases (before the stream opens, as JSON envelope):**
| Status | Condition |
|--------|-----------|
| 422 | empty question (`EMPTY_QUESTION`) |
| 404 | conversation not found (`NOT_FOUND`) |
| 409 | a query is already running on this conversation (`RUN_IN_PROGRESS`) |

A fatal run failure (LLM down, dataset not loaded) is reported **inside** the stream as an `error`
event, not an HTTP status, since the stream has already opened.

---

### `GET /conversations/{conversation_id}`

**Purpose:** Get the conversation with its full message history (for reload / display).

**Response:**
```json
{ "ok": true, "data": { "id": "uuid", "dataset_id": "uuid", "title": null, "created_at": "datetime",
  "messages": [
    { "id": "uuid", "conversation_id": "uuid", "run_id": null, "role": "user",
      "content": "total sales by region", "result_table": null, "trace": null, "created_at": "datetime" },
    { "id": "uuid", "conversation_id": "uuid", "run_id": "uuid", "role": "assistant",
      "content": "Total sales by region: …",
      "result_table": { "columns": ["region","total"], "rows": [["West", 4200]] },
      "trace": [ { "description": "Grouping sales by region…", "action": "SELECT …",
                   "result": "…", "is_error": false } ],
      "created_at": "datetime" }
] } }
```

**Error cases:** 404 (`NOT_FOUND`).

## Authentication

First release runs as a **single-deployment, single-tenant** service — no per-user auth. (Auth, roles,
and quotas are deferred — [`01-vision.md`](01-vision.md) § Future Phases.) The `GEMINI_API_KEY` is a
server-side secret, never exposed to clients.
