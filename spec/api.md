# API

---

## API Style

REST over HTTP (FastAPI), single-origin with the UI at `http://localhost:8001`. Responses use the skeleton envelope: success is `{"data": {...}, "error": null}`; errors are HTTP error status with `{"detail": {"code": ..., "message": ...}}`.

**CSV upload shape — chosen:** the CSV is sent as **text in the JSON body** (`csv_text`), alongside `question`. Rationale: the existing skeleton `POST /runs` already takes a JSON body and the frontend already does a JSON `fetch`; sending the CSV as a string keeps the single envelope, avoids adding multipart handling and a second content-type path, and is trivial for the static-export frontend (it reads the file with `FileReader.readAsText`). The size cap (`AGENT_MAX_UPLOAD_BYTES`, 5 MB) bounds the body. This is the simplest shape that works with the existing envelope.

## Endpoints / Commands

### `POST /runs`

**Purpose:** Run one analysis — given a CSV, a question, and an analysis mode, return the computed answer, explanation, the generated code (pandas or SQL), and the result table.

**Request:**
```json
{
  "csv_text": "string — the full CSV file content as text (≤ AGENT_MAX_UPLOAD_BYTES)",
  "question": "string — the natural-language question",
  "mode": "string — 'pandas' (default) or 'sql' (Phase 2+)"
}
```

> `RunRequest` is extended to `{ csv_text: str, question: str, mode?: str }`. The `mode` field defaults to `"pandas"` if omitted (backward compatible with Phase 1). (The legacy `input_text` field is removed from the analyst request; if any back-compat is needed, `question` maps to it server-side.)

**Response (200) — Pandas mode example:**
```json
{
  "data": {
    "run_id": "uuid",
    "status": "completed",
    "mode": "pandas",
    "answer": "Total sales by region, highest first: North 41200, ...",
    "explanation": "I grouped the rows by region and summed the sales column, then sorted descending. North had the highest total at 41,200.",
    "generated_code": "result = df.groupby('region')['sales'].sum().sort_values(ascending=False).reset_index()",
    "result_table": { "columns": ["region", "sales"], "rows": [["North", 41200], ["South", 38050]] },
    "truncated": false,
    "error": null
  },
  "error": null
}
```

**Response (200) — SQL mode example (Phase 2+):**
```json
{
  "data": {
    "run_id": "uuid",
    "status": "completed",
    "mode": "sql",
    "answer": "Total sales by region, highest first: North 41200, ...",
    "explanation": "I grouped the rows by region and summed the sales column, then sorted descending. North had the highest total at 41,200.",
    "generated_code": "SELECT region, SUM(sales) as sales FROM runs GROUP BY region ORDER BY sales DESC",
    "result_table": { "columns": ["region", "sales"], "rows": [["North", 41200], ["South", 38050]] },
    "truncated": false,
    "error": null
  },
  "error": null
}
```

> On a handled failure, the endpoint still returns HTTP 200 with `data.status = "failed"` and `data.error` set (mirrors the skeleton's "error must surface in the body, never silently swallowed" contract). `generated_code` may be present even on failure (so the user can see what was attempted). The `mode` field echoes the request mode.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 422 | Missing `csv_text` or `question` (FastAPI validation) |
| 200 + `data.status = "failed"` | CSV unparseable / over caps, code generation failed, sandbox rejected/errored/timed out, or question unanswerable — `data.error` holds the categorized message |
| 404 | `GET /runs/{id}` for an unknown id |
| 500 | Unexpected internal error (DB write failure) |

### `GET /runs/{run_id}`

**Purpose:** Fetch a previously stored run.

**Response (200):** same `data` shape as `POST /runs`.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | No run with that id |

### `GET /health`

**Purpose:** Liveness. Returns `{"data": {"status": "ok"}, "error": null}`. (Unchanged from skeleton.)

## Authentication

None — single-user local tool bound to localhost. No auth, no API keys for callers.
