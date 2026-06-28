# API

## API Style

REST. All endpoints are prefixed with `/api/`. The frontend calls them via relative paths (single-origin at `http://localhost:8001`). All request/response bodies are JSON except `POST /api/files/upload` which uses `multipart/form-data`. All successful responses follow the existing skeleton envelope: `{"ok": true, "data": {...}}`. All error responses follow: `{"ok": false, "error": {"code": "...", "message": "..."}}`.

## Authentication

None. Single personal user on localhost. No authentication or authorization is implemented.

---

## Endpoints

### `GET /api/health`

**Purpose:** Health check for the server and SQLite database connection.

**Phase:** 1

**Request:** No body.

**Response:**
```json
{
  "ok": true,
  "data": {
    "status": "ok",
    "db": "ok"
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 500 | SQLite unreachable |

---

### `POST /api/files/upload`

**Purpose:** Upload a CSV or Excel file. Stores it on the local filesystem, parses the schema, and records the file in SQLite. Returns a `file_id` and a schema preview for display in the UI.

**Phase:** 1 (CSV); Phase 3 (Excel `.xlsx`/`.xls`)

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | yes | The CSV or Excel file to upload |

**Response:**
```json
{
  "ok": true,
  "data": {
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "original_name": "sales_data.csv",
    "source_type": "csv",
    "row_count": 1250,
    "file_size_bytes": 48320,
    "schema_preview": {
      "columns": ["date", "region", "revenue", "units"],
      "dtypes": {
        "date": "object",
        "region": "object",
        "revenue": "float64",
        "units": "int64"
      },
      "sample_rows": [
        ["2024-01-01", "North", 12500.00, 42],
        ["2024-01-02", "South", 9800.50, 31],
        ["2024-01-03", "East", 15200.75, 58]
      ]
    }
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | File extension not in `.csv`, `.xlsx`, `.xls` |
| 400 | File is empty (0 bytes) |
| 400 | File cannot be parsed as CSV or Excel (malformed) |
| 413 | File exceeds 100 MB |
| 500 | Filesystem write error or SQLite error |

---

### `GET /api/files`

**Purpose:** List all uploaded files with their schema previews. Used to populate the sidebar on page load.

**Phase:** 1

**Request:** No body.

**Response:**
```json
{
  "ok": true,
  "data": {
    "files": [
      {
        "file_id": "550e8400-e29b-41d4-a716-446655440000",
        "original_name": "sales_data.csv",
        "source_type": "csv",
        "row_count": 1250,
        "file_size_bytes": 48320,
        "created_at": "2024-01-15T10:30:00Z",
        "schema_preview": {
          "columns": ["date", "region", "revenue", "units"],
          "dtypes": {"date": "object", "region": "object", "revenue": "float64", "units": "int64"},
          "sample_rows": [["2024-01-01", "North", 12500.00, 42]]
        }
      }
    ]
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 500 | SQLite error |

---

### `POST /api/analysis/run`

**Purpose:** Submit a plain-English question about an uploaded file (or the connected PostgreSQL database in Phase 2). Invokes the LangGraph agent and returns the text answer, Plotly chart spec, and run ID.

**Phase:** 1

**Request:**
```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "What are the top 5 regions by total revenue?",
  "session_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_id` | string (UUID) | yes | Must reference an existing `uploaded_files.id` |
| `question` | string | yes | Plain-English question; 1–2000 characters |
| `session_id` | string \| null | no | Optional session grouping for multi-turn context (Phase 3); ignored in Phase 1 |

**Response (success):**
```json
{
  "ok": true,
  "data": {
    "run_id": "7b6e8a1c-2d4f-4e9a-b3c5-8f0d1e2a3b4c",
    "answer": "The top 5 regions by total revenue are: North ($125,000), East ($98,500), South ($87,200), West ($76,800), and Central ($54,300).",
    "chart_spec": {
      "chart_type": "bar",
      "data": [
        {
          "type": "bar",
          "x": ["North", "East", "South", "West", "Central"],
          "y": [125000, 98500, 87200, 76800, 54300],
          "name": "Total Revenue"
        }
      ],
      "layout": {
        "title": "Top 5 Regions by Total Revenue",
        "xaxis": {"title": "Region"},
        "yaxis": {"title": "Revenue ($)"}
      }
    },
    "status": "completed"
  }
}
```

**Response (failure):**
```json
{
  "ok": true,
  "data": {
    "run_id": "7b6e8a1c-2d4f-4e9a-b3c5-8f0d1e2a3b4c",
    "answer": null,
    "chart_spec": null,
    "status": "failed",
    "error": "Code execution failed: NameError: name 'revenue' is not defined"
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | `file_id` is missing or not a valid UUID |
| 400 | `question` is empty or exceeds 2000 characters |
| 404 | `file_id` does not exist in `uploaded_files` |
| 500 | Unexpected server error (graph invocation crash) |

Note: LLM errors and code execution errors are returned as HTTP 200 with `status: "failed"` and an `error` field — they are expected application-level failures, not HTTP errors.

---

### `GET /api/analysis/runs`

**Purpose:** List past analysis runs. Used for history display and debugging.

**Phase:** 1

**Request query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_id` | string \| null | null | Filter runs by file |
| `limit` | integer | 50 | Max runs to return (1–200) |
| `offset` | integer | 0 | Pagination offset |

**Response:**
```json
{
  "ok": true,
  "data": {
    "runs": [
      {
        "run_id": "7b6e8a1c-2d4f-4e9a-b3c5-8f0d1e2a3b4c",
        "file_id": "550e8400-e29b-41d4-a716-446655440000",
        "question": "What are the top 5 regions by total revenue?",
        "answer": "The top 5 regions by total revenue are...",
        "chart_spec": {"chart_type": "bar", "data": [...], "layout": {...}},
        "status": "completed",
        "error": null,
        "created_at": "2024-01-15T10:35:00Z",
        "completed_at": "2024-01-15T10:35:18Z"
      }
    ],
    "total": 1
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | `limit` out of range |
| 500 | SQLite error |

---

### `POST /api/pg/connect` (Phase 2 stub in Phase 1)

**Purpose:** Test a PostgreSQL connection using `POSTGRES_DSN` from `.env`, introspect table schemas, and register the connection in SQLite.

**Phase:** 2 (stub returns 501 in Phase 1)

**Request:**
```json
{
  "name": "My Analytics DB"
}
```

**Response (Phase 2 real):**
```json
{
  "ok": true,
  "data": {
    "connection_id": "abc12345-...",
    "name": "My Analytics DB",
    "tables": [
      {
        "name": "orders",
        "columns": [
          {"name": "id", "dtype": "integer"},
          {"name": "created_at", "dtype": "timestamp"},
          {"name": "amount", "dtype": "numeric"}
        ]
      }
    ]
  }
}
```

**Response (Phase 1 stub):**
```json
{
  "ok": false,
  "error": {
    "code": "NOT_IMPLEMENTED",
    "message": "PostgreSQL connection is coming in Phase 2."
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | `POSTGRES_DSN` not set in `.env` |
| 502 | Cannot connect to the PostgreSQL server |
| 501 | Phase 1 stub |

---

## Existing Skeleton Endpoints (Retained)

These endpoints from the skeleton are retained unchanged:

| Endpoint | Purpose |
|----------|---------|
| `POST /runs` | Skeleton text-transform run (retained for backward compat; not used by the new UI) |
| `GET /runs/{run_id}` | Get a skeleton run by ID |
| `GET /api/health` | Health check (already listed above) |
