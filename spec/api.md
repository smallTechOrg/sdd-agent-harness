# API

> HTTP contract for the Personal Data Analysis Agent. All responses use the skeleton envelope: success → `{"data": <payload>, "error": null}` (via `ok(data)`); failure → HTTP status + `{"detail": {"code", "message"}}` (via `api_error(code, message, status)`). Single origin: API + static app both on `http://localhost:8001`.

---

## API Style

REST (JSON), served by FastAPI on port 8001. No authentication (single local user). Frontend calls these from the static export at `/app/`.

---

## Phase 1 Endpoints (REAL)

### `GET /health`
**Purpose:** Liveness (skeleton, unchanged).
**Response:** `{"data": {"status": "ok"}, "error": null}`

### `POST /datasets`
**Purpose:** Upload a CSV/Excel file; ingest into DuckDB + parquet; return schema + sample.
**Request:** `multipart/form-data` with `file` (the CSV/.xlsx).
**Response:**
```json
{ "data": {
    "dataset_id": "uuid",
    "name": "sales.csv",
    "schema": [{"name": "month", "dtype": "string"}, {"name": "amount", "dtype": "float64"}],
    "sample": [{"month": "2024-01", "amount": 1200.0}],
    "row_count": 254318
}, "error": null }
```
**Errors:** 400 `BAD_FILE` (unsupported type / parse failure / empty); 413 `TOO_LARGE` (> ~100MB cap); 500 `INGEST_ERROR`.

### `POST /analyses`
**Purpose:** Ask a plain-language question about a dataset; run the LangGraph code-execution loop; return the full answer.
**Request:**
```json
{ "dataset_id": "uuid", "question": "What were total sales by month?" }
```
**Response:**
```json
{ "data": {
    "run_id": "uuid",
    "status": "completed",
    "stage": "done",
    "answer": "Total sales rose each month; March was highest at ...",
    "key_numbers": {"highest_month": "2024-03", "highest_total": 98230.0},
    "summary_table": {"columns": ["month", "total"], "rows": [["2024-01", 81200.0]]},
    "chart_spec": { "data": [...], "layout": {...} },
    "code": "import pandas as pd\nresult = ...",
    "llm_payload": {"schema": [...], "sample": [...], "prior_result": null},
    "tokens_in": 1240, "tokens_out": 320, "cost_estimate": 0.0007,
    "flagged": false
}, "error": null }
```
**Errors:** 404 `DATASET_NOT_FOUND`; 400 `EMPTY_QUESTION`; 422 `ANALYSIS_FAILED` (graph set error — includes attempted code in message when available); 500 `INTERNAL`.

> Phase 1 is synchronous: `POST /analyses` returns when the run completes (well under 30s). The frontend may show staged progress by reading `stage` via `GET /analyses/{id}` while awaiting, but the authoritative result is the POST response.

### `GET /analyses/{run_id}`
**Purpose:** Fetch a run (for staged-progress polling and run history).
**Response:** same shape as the `POST /analyses` `data`, plus `started_at`, `completed_at`, `revisions`, `error_message`.
**Errors:** 404 `RUN_NOT_FOUND`.

### `GET /datasets/{dataset_id}`
**Purpose:** Fetch dataset metadata (schema, sample, row_count).
**Response:** same shape as the `POST /datasets` `data`.
**Errors:** 404 `DATASET_NOT_FOUND`.

---

## Later-phase Endpoints (STUBS in Phase 1 — return 501 `NOT_IMPLEMENTED` or are absent; the UI labels them "coming soon")

| Phase | Endpoint | Purpose |
|-------|----------|---------|
| 2 | `POST /sessions`, `GET /sessions`, `GET /sessions/{id}` | Create/list/resume persistent sessions |
| 2 | `GET /datasets/{id}/profile` | Full column profile |
| 3 | `GET /analyses/{id}/stream` (SSE, `text/event-stream`) | Live streamed stage + answer chunks + cost events |
| 3 | `GET /cost/daily` | Running daily cost total |
| 3 | `GET|POST /datasets/{id}/notes` | Column notes & business rules |
| 4 | `POST /analyses/{id}/export` | Export result CSV / chart PNG / report |
| 4 | `POST /saved-datasets`, `GET /saved-datasets` | Save/reuse a derived dataset |
| 4 | `GET /library`, `POST /analyses/{id}/rerun` | Analysis library + re-run |
| 5 | `POST /connections` | Attach a local DuckDB/SQLite source |
| 5 | `POST /datasets/joins` | Multi-file upload + inferred relationships |

**Streaming shape (Phase 3, SSE):** `event: stage` `data: {"stage": "running"}` → repeated `event: chunk` `data: {"text": "..."}` → `event: cost` `data: {"tokens_in":..,"tokens_out":..,"cost_estimate":..}` → `event: done` `data: {"run_id": "uuid"}`. Chosen over WebSockets for one-directional simplicity with the static-export origin.

## Authentication

None — single local user, localhost only.
