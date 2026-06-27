# API

## API Style

REST over HTTP. All endpoints return JSON using the envelope `{ "data": ..., "error": null | { "code": str, "message": str } }` — the same pattern as the existing `/runs` endpoints in `src/api/_common.py`.

## Authentication

None. This is a single-user local application.

---

## Endpoints

### `GET /health`

**Purpose:** Liveness check. Already implemented in `src/api/health.py`.

**Response:**
```json
{ "data": { "status": "ok" }, "error": null }
```

---

### `POST /uploads`

**Purpose:** Accept a CSV or Excel file upload. Save to local filesystem. Extract and store metadata. Return upload record.

**Request:** `multipart/form-data`

| Field | Type | Required |
|-------|------|----------|
| file | binary (file part) | Yes |

Accepted extensions: `.csv`, `.xlsx`, `.xls`. Max size: 50 MB.

**Response (200 OK):**
```json
{
  "data": {
    "upload_id": "uuid-string",
    "filename": "sales_data.csv",
    "row_count": 1500,
    "col_count": 8,
    "columns": [
      { "name": "date", "dtype": "object" },
      { "name": "sales", "dtype": "float64" },
      { "name": "region", "dtype": "object" }
    ]
  },
  "error": null
}
```

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 413 | FILE_TOO_LARGE | File exceeds 50 MB |
| 422 | UNSUPPORTED_FORMAT | Extension is not .csv, .xlsx, or .xls |
| 500 | FILE_SAVE_ERROR | Could not write file to disk |
| 500 | PARSE_ERROR | pandas could not read the file |

---

### `GET /uploads`

**Purpose:** List all uploaded files, ordered by upload date descending. Used to populate the sidebar history.

**Request:** No body. No query parameters (returns all uploads; there is no pagination in Phase 1).

**Response (200 OK):**
```json
{
  "data": [
    {
      "upload_id": "uuid-string",
      "filename": "sales_data.csv",
      "row_count": 1500,
      "col_count": 8,
      "uploaded_at": "2026-06-28T10:30:00Z"
    }
  ],
  "error": null
}
```

Returns an empty list if no uploads exist.

---

### `POST /analyses`

**Purpose:** Run an analysis on a previously uploaded file. Invokes the LangGraph pipeline synchronously and returns the completed result.

**Request:** `application/json`

```json
{
  "upload_id": "uuid-string",
  "analysis_type": "summary_stats",
  "params": {},
  "question": null
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| upload_id | string | Yes | Must match an existing upload |
| analysis_type | string | Yes | One of: summary_stats, trend_over_time, top_bottom_n, correlation, nl_query |
| params | object | No | Type-specific parameters (see below) |
| question | string or null | Only for nl_query | Free-text question |

Params by analysis_type:

- `summary_stats`: `{}` (no params needed)
- `trend_over_time`: `{ "date_col": "date", "value_col": "sales" }`
- `top_bottom_n`: `{ "col": "sales", "n": 10, "direction": "top" }`
- `correlation`: `{ "col_a": "sales", "col_b": "units" }`
- `nl_query`: `{}` (question goes in the `question` field)

**Response (200 OK — completed):**
```json
{
  "data": {
    "analysis_id": "uuid-string",
    "status": "completed",
    "analysis_type": "summary_stats",
    "summary": "Dataset has 1500 rows and 8 columns. Sales column: mean 4200.5, median 3900, min 100, max 12000.",
    "chart_json": "{\"data\": [...], \"layout\": {...}}",
    "table": [
      { "column": "sales", "count": 1500, "mean": 4200.5, "median": 3900.0, "min": 100.0, "max": 12000.0, "std": 2100.3 }
    ],
    "error_message": null
  },
  "error": null
}
```

**Response (200 OK — failed):**
```json
{
  "data": {
    "analysis_id": "uuid-string",
    "status": "failed",
    "analysis_type": "trend_over_time",
    "summary": null,
    "chart_json": null,
    "table": null,
    "error_message": "Column 'date_col' could not be parsed as datetime."
  },
  "error": null
}
```

Note: A failed analysis still returns HTTP 200 with `status: "failed"` in the data. HTTP 4xx/5xx are reserved for request-level errors (invalid upload_id format, unknown analysis_type, etc.).

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | NOT_FOUND | upload_id does not exist in the uploads table |
| 422 | INVALID_ANALYSIS_TYPE | analysis_type is not one of the five valid values |
| 422 | MISSING_PARAMS | Required params are absent for the given analysis_type |
| 422 | MISSING_QUESTION | analysis_type is nl_query but question is null or empty |

---

### `GET /analyses/{analysis_id}`

**Purpose:** Retrieve the result of a previously run analysis by its ID.

**Path parameter:** `analysis_id` — UUID string

**Response (200 OK):**

Same shape as the `data` field in `POST /analyses` response above.

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | NOT_FOUND | analysis_id does not exist |

---

## Response Envelope

Every response — success or error — uses this envelope:

```json
{
  "data": { ... } | null,
  "error": null | { "code": "ERROR_CODE", "message": "Human-readable message." }
}
```

HTTP status codes:
- 200: request processed (check `data.status` for analysis success/failure)
- 404: resource not found
- 413: payload too large
- 422: validation error (malformed request, unsupported type)
- 500: unexpected server error

The `ok()` and `api_error()` helpers in `src/api/_common.py` implement this envelope and must be used by all new routes.
