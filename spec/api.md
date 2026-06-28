# API

## API Style

REST over HTTP/1.1 with one Server-Sent Events (SSE) endpoint for streaming query answers. All endpoints are under the `/api/` prefix. No authentication — single-user local tool.

---

## Endpoints

### `POST /api/files/upload`

**Purpose:** Accept a multipart CSV (or Excel in Phase 3) file upload, save it to `uploads/`, run the profiler, write a row to `uploaded_files`, and return the file ID and full profile.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | `UploadFile` | yes | The CSV or Excel file |
| `session_id` | `string` | no | UUID of the current session (Phase 2+); ignored in Phase 1 |

**Response:** `200 OK`, `application/json`

```json
{
  "file_id": "3f7c1a2e-...",
  "original_filename": "sales_2025.csv",
  "profile": {
    "columns": [
      {
        "name": "date",
        "dtype": "object",
        "null_count": 0,
        "sample_values": ["2025-01-01", "2025-01-02", "2025-01-03"]
      },
      {
        "name": "revenue",
        "dtype": "float64",
        "null_count": 2,
        "sample_values": [1200.50, 980.00, 1450.75]
      }
    ],
    "row_count": 1250,
    "column_count": 5,
    "file_size_bytes": 48200,
    "profiled_at": "2026-06-28T10:23:45Z"
  }
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 400 | File extension is not `.csv` or `.xlsx` |
| 413 | File exceeds 100 MB |
| 500 | Filesystem write failed or profiler raised an unhandled exception |

---

### `POST /api/query/stream`

**Purpose:** Accept a natural-language question and one or more file IDs, run the LangGraph agent, and stream the answer back as Server-Sent Events.

**Request:** `application/json`

```json
{
  "question": "What are the top 5 products by revenue?",
  "file_ids": ["3f7c1a2e-..."],
  "session_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | `string` | yes | Natural-language question (max 2000 chars) |
| `file_ids` | `array[string]` | yes | One or more `uploaded_files.id` values; must be non-empty |
| `session_id` | `string \| null` | no | Session ID for history tracking (Phase 2+); ignored in Phase 1 |

**Response:** `200 OK`, `text/event-stream`

SSE event types emitted in order:

```
data: {"type": "run_start", "query_run_id": "abc123..."}

data: {"type": "token", "text": "The top 5 products"}
data: {"type": "token", "text": " by revenue are..."}

data: {"type": "code_step", "iteration": 1, "code": "import pandas as pd\n...", "stdout": "[{...}]", "stderr": "", "success": true}

data: {"type": "chart", "plotly": {"data": [...], "layout": {...}}}

data: {"type": "cost", "input_tokens": 1240, "output_tokens": 380, "cost_usd": 0.000298}

data: {"type": "done"}
```

On error:

```
data: {"type": "error", "message": "Failed to execute code after 5 attempts: ..."}
```

On clarification needed:

```
data: {"type": "clarification", "question": "Did you mean column 'rev' or 'revenue'?"}
```

**Error cases (before stream opens):**

| Status | Condition |
|--------|-----------|
| 400 | `question` is empty, `file_ids` is empty, or any `file_id` does not exist |
| 500 | Agent graph failed to initialise |

---

### `GET /api/files`

**Purpose:** List all uploaded files for the current user (or session in Phase 2).

**Request:** No body. Optional query parameter `session_id` (Phase 2).

**Response:** `200 OK`, `application/json`

```json
{
  "files": [
    {
      "file_id": "3f7c1a2e-...",
      "original_filename": "sales_2025.csv",
      "file_size_bytes": 48200,
      "row_count": 1250,
      "column_count": 5,
      "created_at": "2026-06-28T10:23:45Z"
    }
  ]
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 500 | DB read error |

---

### `GET /api/sessions` (Phase 2 stub in Phase 1)

**Purpose:** List all sessions ordered by `last_active_at` descending.

**Phase 1 behaviour:** Returns an empty list `{"sessions": []}` — the endpoint exists so the frontend can call it without errors, but it is a stub.

**Response:** `200 OK`, `application/json`

```json
{
  "sessions": [
    {
      "session_id": "7a2d1f...",
      "name": "Session 2026-06-28",
      "created_at": "2026-06-28T09:00:00Z",
      "last_active_at": "2026-06-28T10:30:00Z",
      "query_count": 5
    }
  ]
}
```

---

### `GET /api/sessions/{session_id}/queries` (Phase 2)

**Purpose:** Return all query runs for a session, ordered by `started_at` descending.

**Response:** `200 OK`, `application/json`

```json
{
  "queries": [
    {
      "query_run_id": "abc123...",
      "question": "What are the top 5 products?",
      "answer_text": "The top 5 products by revenue are...",
      "plotly_chart_json": "{...}",
      "status": "completed",
      "input_tokens": 1240,
      "output_tokens": 380,
      "cost_usd": 0.000298,
      "started_at": "2026-06-28T10:23:45Z",
      "completed_at": "2026-06-28T10:23:52Z"
    }
  ]
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 404 | `session_id` not found |

---

### `GET /api/audit` (Phase 2)

**Purpose:** Return the full audit log, paginated, ordered by `recorded_at` descending. Used for debugging and cost review.

**Request:** Optional query parameters: `limit` (default 50, max 500), `offset` (default 0), `date` (ISO date string, filter by `recorded_at` date).

**Response:** `200 OK`, `application/json`

```json
{
  "total": 42,
  "entries": [
    {
      "id": "...",
      "query_run_id": "abc123...",
      "question": "What are the top 5 products?",
      "answer_text": "...",
      "input_tokens": 1240,
      "output_tokens": 380,
      "cost_usd": 0.000298,
      "elapsed_s": 4.2,
      "status": "completed",
      "recorded_at": "2026-06-28T10:23:52Z"
    }
  ]
}
```

---

### `GET /api/cost/daily` (Phase 3)

**Purpose:** Return the running cost total for the current UTC day.

**Response:** `200 OK`, `application/json`

```json
{
  "date": "2026-06-28",
  "total_cost_usd": 0.00412,
  "query_count": 14
}
```

---

### `GET /health`

**Purpose:** Liveness check. Returns 200 with app version.

**Response:** `200 OK`, `application/json`

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## Authentication

None. Single-user local tool — the user runs the server themselves on their own machine. No API tokens, sessions, or auth headers required.
