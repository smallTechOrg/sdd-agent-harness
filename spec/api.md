# API — Programmatic Contract

This document is the binding contract between callers (UI, tests, other services) and the server. Frontend and backend can be built in parallel against it without further conversation.

Cross-references:
- Port numbers owned by architecture.md / vision.md Hard Constraints.
- SC-N in vision.md; PN-ACn in delivery-plan.md.
- `audit_log` columns in data-model.md §audit_log.
- `stub_mode` flag defined once in §GET /health (Stub Mode Signalling).

---

## Surface & Conventions

| Convention | Value | Notes |
|------------|-------|-------|
| API style | REST over HTTP/JSON | multipart for file uploads only |
| Base URL | `http://localhost:8001` | port owned by architecture.md; do not redefine here |
| Request content type | `application/json` | except POST /datasets: `multipart/form-data` |
| Response content type | `application/json` | all endpoints |
| Charset | `utf-8` | |
| Id format | `str (uuid4)` | all resource ids; ≤ 36 chars |
| Timestamp format | `ISO-8601 UTC` (e.g. `2026-06-22T04:10:00Z`) | all `*_at` fields |
| Pagination | No pagination — list endpoints return the full set; bounded by vision.md Hard Constraints (max 20 datasets/session, max 10 000 result rows) | |
| Success status policy | reads: 200; creates: **201 + `Location`**; long-running async: 202 | POST /query runs synchronously (≤ 30 s); no 202 needed |
| Error envelope | See canonical block below | every non-2xx body uses this exact shape |
| CORS | `DAA_CORS_ORIGINS` (default `http://localhost:3000`) | architecture.md env var |

**Canonical error envelope (ALL non-2xx responses):**

```json
{
  "error": {
    "code": "string — SCREAMING_SNAKE machine code, stable, from each endpoint's matrix",
    "message": "string — human-readable, safe to surface in the UI toast"
  }
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `IF any endpoint returns a non-2xx status, THEN the body SHALL match the canonical error envelope with a non-empty error.code and a non-empty error.message.` | `pytest tests/test_api.py::test_error_envelope_shape` — POST /query with unknown dataset_id; `assert r.json()["error"]["code"] == "NO_DATASET" and r.json()["error"]["message"] != ""` |

---

## Endpoints

| METHOD /path | Phase | Purpose (one line) | Traces (must resolve) |
|--------------|-------|--------------------|-----------------------|
| `GET /health` | Phase 1 | Liveness + stub/live signal | SC-STUB (P1-AC2) |
| `POST /sessions` | Phase 1 | Create a new conversation session | SC-7 (P1-AC10) |
| `GET /sessions` | Phase 1 | List all sessions | SC-7 (P1-AC10) |
| `POST /datasets` | Phase 1 | Upload and register a tabular file | SC-CORE (P1-AC4) |
| `GET /datasets` | Phase 1 | List datasets for a session | SC-CORE (P1-AC4) |
| `POST /query` | Phase 1 | Submit NL question; returns answer | SC-CORE (P1-AC3) |
| `GET /query/{id}/audit` | Phase 2 | Retrieve audit log rows for a query run | SC-6 (P2-AC2) |
| `GET /sessions/{id}/history` | Phase 2 | Retrieve conversation history for a session | SC-7 (P2-AC7) |
| `DELETE /datasets/{id}` | Phase 3 | Delete a dataset (registry + DuckDB table) | SC-CORE (P3-AC1) |
| `DELETE /sessions/{id}` | Phase 3 | Delete a session and all its data | SC-7 (P3-AC2) |

---

### `GET /health`  (→ Phase 1)

**Purpose:** report liveness and whether the server is serving canned stub data or live LLM data.

**Traces:** SC-STUB "IF DAA_LLM_PROVIDER=stub THEN the system SHALL pass the full unit suite with no key and no network" · P1-AC2 "WHILE DAA_LLM_PROVIDER=stub, GET /health SHALL return 200 with stub_mode:true"

**Request:** none.

**Response 200:**
```json
{
  "status": "string — literal \"ok\" while the process is serving",
  "stub_mode": "bool — true WHEN DAA_LLM_PROVIDER=stub, else false"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 503 | `SERVICE_UNAVAILABLE` | returned before `create_tables_sqlite()` completes (readiness probe); architecture.md Startup Sequence step 4 |

**Stub shape (Phase 1):** `{"status":"ok","stub_mode":true}` — no network, no key.

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHILE DAA_LLM_PROVIDER=stub, GET /health SHALL return 200 with body {"status":"ok","stub_mode":true} and SHALL make no network call.` | `pytest tests/test_health.py::test_health_stub_offline` (ALLOW_MODEL_REQUESTS=False) — `assert r.status_code == 200 and r.json() == {"status":"ok","stub_mode":True}` |

---

### `POST /sessions`  (→ Phase 1)

**Purpose:** create a new conversation session and return its id.

**Traces:** SC-7 "WHILE a session exists after a server restart, the session record SHALL be retrievable" · P1-AC10 "WHEN POST /sessions is called, the system SHALL return 201 with a non-empty session id"

**Request:** none (no body).

**Response 201:**
```json
{
  "id": "string (uuid4) — the new session id",
  "created_at": "ISO-8601 UTC — session creation timestamp"
}
```
`Location: /sessions/{id}`

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 500 | `INTERNAL` | unexpected failure writing to SQLite spine |

**Stub shape (Phase 1):**
```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "created_at": "2026-06-22T00:00:00Z"
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN POST /sessions is called, the system SHALL return 201 with a non-empty id string (uuid4 format) and a Location header.` | `pytest tests/test_sessions.py::test_create_session` — `assert r.status_code == 201 and len(r.json()["id"]) == 36 and "Location" in r.headers` |

---

### `GET /sessions`  (→ Phase 1)

**Purpose:** list all sessions ordered by creation time descending.

**Traces:** SC-7 · P1-AC10

**Request:** none.

**Response 200:**
```json
{
  "sessions": "array<object{id: string, created_at: ISO-8601, title: string|null}> — ordered newest first; length >= 0"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 500 | `INTERNAL` | unexpected failure reading SQLite spine |

**Stub shape (Phase 1):**
```json
{
  "sessions": [
    {"id": "00000000-0000-0000-0000-000000000001", "created_at": "2026-06-22T00:00:00Z", "title": null}
  ]
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN ≥1 session has been created, GET /sessions SHALL return an array whose first element has a non-empty id field.` | `pytest tests/test_sessions.py::test_list_sessions` — create 1 session first; `assert len(r.json()["sessions"]) >= 1 and r.json()["sessions"][0]["id"] != ""` |

---

### `POST /datasets`  (→ Phase 1)

**Purpose:** upload a tabular file, register it in the dataset registry, and ingest it into DuckDB as a persistent table.

**Traces:** SC-CORE · P1-AC4 "WHEN a CSV/JSON/Excel/Parquet file is uploaded, GET /datasets SHALL return it with name, row_count ≥ 1, and uploaded_at"

**Request:** `multipart/form-data`

| part | type | required | constraint | meaning |
|------|------|----------|-----------|---------|
| file | file | yes | content-type one of: text/csv, application/json, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/octet-stream (Parquet); ≤ 200 MB | the tabular file to ingest |
| session_id | string | yes | uuid4 format; must exist in session table | the session to attach this dataset to |

**Response 201:**
```json
{
  "id": "string (uuid4) — the new dataset id",
  "name": "string — original filename; ≤ 255 chars",
  "file_format": "string — one of: csv, json, excel, parquet",
  "row_count": "int >= 0 — number of rows ingested into DuckDB",
  "size_bytes": "int >= 0 — raw file size in bytes",
  "column_schema": "array<object{name: string, dtype: string, nullable: bool, sample: string|null}> — one entry per column",
  "duckdb_table": "string — DuckDB table name, always 'dataset_<id>'",
  "uploaded_at": "ISO-8601 UTC"
}
```
`Location: /datasets/{id}`

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 422 | `UNSUPPORTED_FILE` | content-type not in allowed set, or file cannot be parsed |
| 413 | `FILE_TOO_LARGE` | file exceeds 200 MB (DAA_MAX_UPLOAD_BYTES) |
| 404 | `NO_SESSION` | session_id not found in SQLite spine |
| 422 | `BAD_INPUT` | session_id not uuid4 format |
| 500 | `INTERNAL` | unexpected failure during DuckDB ingest |

**Stub shape (Phase 1):**
```json
{
  "id": "00000000-0000-0000-0000-000000000010",
  "name": "sample.csv",
  "file_format": "csv",
  "row_count": 100,
  "size_bytes": 4096,
  "column_schema": [
    {"name": "product", "dtype": "TEXT", "nullable": false, "sample": "Widget A"},
    {"name": "revenue", "dtype": "DOUBLE", "nullable": false, "sample": "1000.00"},
    {"name": "category", "dtype": "TEXT", "nullable": true, "sample": "Electronics"}
  ],
  "duckdb_table": "dataset_00000000000000000000000000000010",
  "uploaded_at": "2026-06-22T00:00:00Z"
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN a valid CSV file is uploaded, the system SHALL return 201 with row_count >= 1 and a non-empty column_schema array.` | `pytest tests/test_datasets.py::test_upload_csv` — upload `tests/fixtures/sample.csv` (100 rows); `assert r.status_code == 201 and r.json()["row_count"] >= 1 and len(r.json()["column_schema"]) >= 1` |
| `IF the uploaded file exceeds 200 MB, THEN the system SHALL return 413 with error.code == "FILE_TOO_LARGE".` | `pytest tests/test_datasets.py::test_upload_too_large` — `assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"` |
| `IF the uploaded file is not a supported format (e.g. a PNG), THEN the system SHALL return 422 with error.code == "UNSUPPORTED_FILE".` | `pytest tests/test_datasets.py::test_upload_unsupported` — upload `tests/fixtures/broken.png`; `assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"` |

---

### `GET /datasets`  (→ Phase 1)

**Purpose:** list all datasets registered in a session, ordered by upload time descending.

**Traces:** SC-CORE · P1-AC4

**Request:** `?session_id=<uuid4> required`

**Response 200:**
```json
{
  "datasets": "array<object{id: string, name: string, file_format: string, row_count: int, size_bytes: int, column_schema: array<object>, duckdb_table: string, uploaded_at: ISO-8601}> — ordered newest first; length >= 0"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 422 | `BAD_INPUT` | session_id missing or not uuid4 format |
| 404 | `NO_SESSION` | session_id not found |
| 500 | `INTERNAL` | unexpected failure |

**Stub shape (Phase 1):**
```json
{
  "datasets": [
    {
      "id": "00000000-0000-0000-0000-000000000010",
      "name": "sample.csv",
      "file_format": "csv",
      "row_count": 100,
      "size_bytes": 4096,
      "column_schema": [
        {"name": "product", "dtype": "TEXT", "nullable": false, "sample": "Widget A"},
        {"name": "revenue", "dtype": "DOUBLE", "nullable": false, "sample": "1000.00"}
      ],
      "duckdb_table": "dataset_00000000000000000000000000000010",
      "uploaded_at": "2026-06-22T00:00:00Z"
    }
  ]
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN ≥1 dataset is uploaded to a session, GET /datasets SHALL return an array with each dataset having name, row_count >= 1, and uploaded_at.` | `pytest tests/test_datasets.py::test_list_datasets` — upload sample.csv first; `assert len(r.json()["datasets"]) >= 1 and r.json()["datasets"][0]["row_count"] >= 1 and r.json()["datasets"][0]["name"] != ""` |

---

### `POST /query`  (→ Phase 1)

**Purpose:** submit a natural-language question, run the NL→SQL→DuckDB agent pipeline, and return the result.

**Traces:** SC-CORE "WHEN a NL question is submitted, API SHALL return rows length >= 1 and non-empty sql" · SC-UX "WHEN query returns numeric data, UI SHALL render a Plotly chart" · SC-6 "WHEN SQL executes, audit_log row written" · P1-AC3 · P2-AC1 · P3-AC3

**Request:**
```json
{
  "session_id": "string required (uuid4) — id of an existing session",
  "question": "string required [1..2000 chars] — the natural-language question",
  "dataset_ids": "array<string> required (each uuid4) [min 1 element] — ids of datasets to query; each must exist in this session"
}
```

**Response 200:**
```json
{
  "query_run_id": "string (uuid4) — id of the query_run row",
  "sql": "string — the executed read-only SELECT SQL; non-empty on success",
  "columns": "array<string> — column names in result order; length >= 1 on success",
  "rows": "array<object{<col>: string|int|float|bool|null}> — query result rows; length >= 0",
  "row_count": "int >= 0 — total rows returned",
  "chart_spec": "object{data: array, layout: object} | null — Plotly chart spec; null when result has no chartable columns",
  "suggestions": "array<string> — follow-up question suggestions; length >= 0; populated in Phase 3",
  "table_markdown": "string — GFM Markdown table of the first min(row_count, 50) rows; non-empty when row_count >= 1",
  "stub_mode": "bool — true when DAA_LLM_PROVIDER=stub"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 422 | `BAD_INPUT` | question empty, exceeds 2000 chars, or dataset_ids empty |
| 404 | `NO_SESSION` | session_id not found |
| 404 | `NO_DATASET` | any dataset_id in dataset_ids not found |
| 422 | `BAD_SQL` | generated SQL is not a valid SELECT or fails the guard predicate |
| 422 | `QUERY_ERROR` | valid SQL but DuckDB returns a runtime error |
| 504 | `LLM_TIMEOUT` | LLM call exceeds DAA_REQUEST_TIMEOUT_S |
| 502 | `LLM_ERROR` | non-2xx response from Google Gemini API after retries |
| 409 | `RUN_ACTIVE` | another query run is already active for this session |
| 500 | `INTERNAL` | unexpected failure |

**Stub shape (Phase 1):**
```json
{
  "query_run_id": "00000000-0000-0000-0000-000000000100",
  "sql": "SELECT product, SUM(revenue) AS total_revenue FROM dataset_00000000000000000000000000000010 GROUP BY product ORDER BY total_revenue DESC LIMIT 5",
  "columns": ["product", "total_revenue"],
  "rows": [
    {"product": "Widget A", "total_revenue": 5000.0},
    {"product": "Widget B", "total_revenue": 4200.0},
    {"product": "Widget C", "total_revenue": 3800.0},
    {"product": "Widget D", "total_revenue": 3100.0},
    {"product": "Widget E", "total_revenue": 2900.0}
  ],
  "row_count": 5,
  "chart_spec": {
    "data": [{"type": "bar", "x": ["Widget A","Widget B","Widget C","Widget D","Widget E"], "y": [5000.0,4200.0,3800.0,3100.0,2900.0], "name": "total_revenue"}],
    "layout": {"title": "Top 5 Products by Revenue", "xaxis": {"title": "product"}, "yaxis": {"title": "total_revenue"}}
  },
  "suggestions": ["Break down by category", "Show revenue trend over time"],
  "table_markdown": "| product | total_revenue |\n|---------|---------------|\n| Widget A | 5000.0 |\n| Widget B | 4200.0 |\n| Widget C | 3800.0 |\n| Widget D | 3100.0 |\n| Widget E | 2900.0 |",
  "stub_mode": true
}
```

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN a question is submitted with a valid dataset_id, the system SHALL return 200 with rows length >= 1, a non-empty sql string, and a non-empty table_markdown string.` | `pytest tests/test_query.py::test_query_returns_rows` — `assert r.status_code == 200 and len(r.json()["rows"]) >= 1 and r.json()["sql"] != "" and r.json()["table_markdown"] != ""` |
| `WHEN the query result has a numeric column, the response SHALL include a chart_spec with a non-empty data array and non-empty layout.xaxis.title.` | `pytest tests/test_query.py::test_chart_spec_present` — `assert r.json()["chart_spec"] is not None and len(r.json()["chart_spec"]["data"]) >= 1 and r.json()["chart_spec"]["layout"]["xaxis"]["title"] != ""` |
| `IF the question field is empty, THEN the system SHALL return 422 with error.code == "BAD_INPUT".` | `pytest tests/test_query.py::test_empty_question` — `assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_INPUT"` |
| `IF a dataset_id does not exist in the session, THEN the system SHALL return 404 with error.code == "NO_DATASET".` | `pytest tests/test_query.py::test_bad_dataset` — `assert r.status_code == 404 and r.json()["error"]["code"] == "NO_DATASET"` |

---

### `GET /query/{id}/audit`  (→ Phase 2)

**Purpose:** retrieve the audit log rows for a specific query run (SQL execution + LLM call records).

**Traces:** SC-6 "WHEN SQL query executes, system SHALL append exactly 1 audit_log row" · P2-AC2

**Request:** path param `id: string required (uuid4)`

**Response 200:**
```json
{
  "audit_rows": "array<object{id: int, action: string, payload: string, rows_affected: int|null, duration_ms: int, model: string|null, input_tokens: int|null, output_tokens: int|null, created_at: ISO-8601}> — ordered by created_at asc; length >= 0"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 404 | `NO_QUERY_RUN` | query run id not found |
| 422 | `BAD_INPUT` | id not uuid4 format |
| 500 | `INTERNAL` | unexpected failure |

**Stub shape (Phase 1):** Not available in Phase 1 (Phase 2 endpoint). Returns 404 in Phase 1.

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN a query run completes, GET /query/{id}/audit SHALL return at least 1 audit_row with action='sql' and duration_ms >= 0.` | `pytest tests/test_audit.py::test_get_audit_rows` — run a query; `assert len(r.json()["audit_rows"]) >= 1 and any(row["action"] == "sql" and row["duration_ms"] >= 0 for row in r.json()["audit_rows"])` |

---

### `GET /sessions/{id}/history`  (→ Phase 2)

**Purpose:** retrieve the conversation history (user questions + assistant answers) for a session.

**Traces:** SC-7 · P2-AC7

**Request:** path param `id: string required (uuid4)`; query param `?limit: int optional [1..100] default 50`

**Response 200:**
```json
{
  "session_id": "string (uuid4)",
  "messages": "array<object{id: string, role: string, content: string, query_run_id: string|null, created_at: ISO-8601}> — ordered by created_at asc; length >= 0"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 404 | `NO_SESSION` | session id not found |
| 422 | `BAD_INPUT` | id not uuid4 format or limit out of [1..100] |
| 500 | `INTERNAL` | unexpected failure |

**Stub shape (Phase 1):** Not available in Phase 1. Returns 404 in Phase 1.

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN a session has ≥1 completed query, GET /sessions/{id}/history SHALL return messages with length >= 2 (one user, one assistant).` | `pytest tests/test_sessions.py::test_session_history` — run 1 query; `assert len(r.json()["messages"]) >= 2 and r.json()["messages"][0]["role"] == "user"` |

---

### `DELETE /datasets/{id}`  (→ Phase 3)

**Purpose:** delete a dataset from the registry and drop its DuckDB table.

**Traces:** SC-CORE (Non-Scope "→ Phase 3") · P3-AC1

**Request:** path param `id: string required (uuid4)`

**Response 200:**
```json
{
  "deleted": "bool — true on success",
  "id": "string (uuid4) — the deleted dataset id"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 404 | `NO_DATASET` | dataset id not found |
| 422 | `BAD_INPUT` | id not uuid4 format |
| 500 | `INTERNAL` | unexpected DuckDB DROP TABLE failure |

**Stub shape (Phase 1):** Not available Phase 1–2. Returns 404 in Phase 1–2.

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN DELETE /datasets/{id} is called on an existing dataset, the system SHALL return 200 with deleted=true and the DuckDB table SHALL no longer exist.` | `pytest tests/test_datasets.py::test_delete_dataset` — upload then delete; `assert r.status_code == 200 and r.json()["deleted"] == True`; then `GET /datasets?session_id=<s>` — `assert len([d for d in r.json()["datasets"] if d["id"] == deleted_id]) == 0` |

---

### `DELETE /sessions/{id}`  (→ Phase 3)

**Purpose:** delete a session and all its associated datasets, queries, and audit records (CASCADE).

**Traces:** SC-7 · P3-AC2

**Request:** path param `id: string required (uuid4)`

**Response 200:**
```json
{
  "deleted": "bool — true on success",
  "id": "string (uuid4) — the deleted session id"
}
```

**Error matrix:**

| Status | code | Condition |
|--------|------|-----------|
| 404 | `NO_SESSION` | session id not found |
| 422 | `BAD_INPUT` | id not uuid4 format |
| 500 | `INTERNAL` | unexpected failure |

**Stub shape (Phase 1–2):** Not available. Returns 404 in Phase 1–2.

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHEN DELETE /sessions/{id} is called, the system SHALL return 200, all child datasets SHALL be removed, and GET /sessions SHALL not include the deleted id.` | `pytest tests/test_sessions.py::test_delete_session` — `assert r.status_code == 200 and r.json()["deleted"] == True`; `GET /sessions` — `assert not any(s["id"] == deleted_id for s in r.json()["sessions"])` |

---

## Authentication

| Aspect | Value |
|--------|-------|
| Scheme | none (local demo by design) |
| Header name + format | n/a |
| Applies to | n/a — all endpoints are unauthenticated |
| Phase auth is introduced | never (by design) |
| Cross-ref | vision.md Non-Scope: "Multi-user auth / RBAC — never — single-tenant local tool by design" |

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `The server SHALL read no auth header and SHALL serve every endpoint to any local caller.` | `pytest tests/test_api.py::test_no_auth_required` — call `GET /health` with no headers; `assert r.status_code == 200` |

---

## Stub Mode Signalling

| Aspect | Value |
|--------|-------|
| Signal field | `stub_mode: bool` in `GET /health` (defined once in §Endpoints) |
| Trigger | `DAA_LLM_PROVIDER=stub` (env var owned by architecture.md) |
| Stub data property | Every stub response is deterministic AND shape-identical to its live counterpart (same fields, same types, non-empty values) — stubbed by VALUE, never by omission |
| Network in stub mode | None — no outbound call, no API key required, on any endpoint |
| Test enforcement | `ALLOW_MODEL_REQUESTS=False` in test suite `conftest.py` — any attempted network call fails the test. Cross-ref harness/rules/testing.md |
| UI consumer | ui.md Stub-Mode Banner reads `stub_mode` from `GET /health` |

| Acceptance criterion (EARS) | Acceptance test (RUNNABLE) |
|-----------------------------|---------------------------|
| `WHILE DAA_LLM_PROVIDER=stub, the entire API surface SHALL respond without a key or network, and POST /query SHALL return a non-empty sql string and rows length >= 1.` | `pytest tests/test_stub.py::test_full_surface_offline` (ALLOW_MODEL_REQUESTS=False, no API key set) — `assert all responses 2xx and r_query.json()["sql"] != "" and len(r_query.json()["rows"]) >= 1` |

---

## Gaps & Assumptions

| Item | Type | Resolution / Owner |
|------|------|--------------------|
| Result streaming (token-by-token) | ASSUMPTION | whole-response delivery; vision.md Non-Scope: "Streaming — never (whole-response delivery; latency ≤ 10 s p95)" |
| Pagination on /query rows | ASSUMPTION | no pagination; rows capped at `DAA_MAX_RESULT_ROWS` (10 000) per vision.md Hard Constraints |
| Prompt caching for token economy | ASSUMPTION | Gemini context caching used in `node_generate_sql`; details in agent-graph.md |
| Multiple simultaneous sessions per server | ASSUMPTION | single-tenant; 1 concurrent run per server instance; 409 if a run is already active |
