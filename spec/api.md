# API

## API Style

REST over HTTP (FastAPI), single-origin with the frontend at `/app/`. All responses use the
baseline envelope from `src/api/_common.py`:

- Success: `{"data": <payload>, "error": null}` via `ok(payload)`.
- Error: HTTP error with `{"detail": {"code": <CODE>, "message": <msg>}}` via `api_error(...)`.

Authentication: **none** — single trusted local user, localhost only.

> Phase markers below indicate which endpoints are real per phase. The frontend is built
> against this contract so frontend and backend slices develop in parallel.

## Endpoints / Commands

### `POST /datasets`  *(Phase 1 — real)*

**Purpose:** upload one spreadsheet; save it to `uploads/`, profile it, persist a `dataset`.

**Request:** `multipart/form-data` with a single `file` field (CSV in P1; XLSX in P4).

**Response:**
```json
{ "data": {
    "id": "uuid",
    "name": "sales.csv",
    "file_type": "csv",
    "row_count": 12873,
    "size_bytes": 5242880,
    "profile": {
      "columns": [{"name":"region","dtype":"object","missing":0,"distinct":5,"top":["West"]}],
      "numeric_stats": {"revenue": {"min":0,"max":9999,"mean":312.4}},
      "sample": [{"region":"West","revenue":120}]
    },
    "created_at": "2026-06-28T12:00:00Z"
  }, "error": null }
```
> `profile.sample` is capped at ≤5 rows; this is the only row-level data anywhere in the API
> and is what (at most) the LLM receives.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | No file / unsupported type / unparseable spreadsheet (`BAD_UPLOAD`) |
| 413 | File exceeds size limit (`FILE_TOO_LARGE`) |
| 500 | Disk write or profiling failure (`PROFILE_FAILED`) |

### `GET /datasets/{id}`  *(Phase 1 — real)*

**Purpose:** fetch a dataset's metadata + profile.
**Response:** same `data` shape as `POST /datasets`.
**Errors:** 404 `NOT_FOUND`.

### `POST /ask`  *(Phase 1 — real; Phase 3 adds streaming variant)*

**Purpose:** ask a natural-language question against a dataset; run the agent; return the
answer with visible code + plan.

**Request:**
```json
{ "dataset_id": "uuid",
  "question": "what is the total revenue by region?",
  "conversation_id": "uuid|null" }
```
> `conversation_id` null → a new conversation is created; otherwise prior turns are loaded as
> context (conversation memory).

**Response:**
```json
{ "data": {
    "run_id": "uuid",
    "conversation_id": "uuid",
    "status": "completed",
    "answer": "Revenue totals: West $1.2M, East $0.9M …",
    "plan": "1. Group by region 2. Sum revenue 3. Sort desc",
    "code": "result = df.groupby('region')['revenue'].sum().sort_values(ascending=False)",
    "result_preview": "region\nWest    1200000\nEast     900000",
    "iterations": 1,
    "suggestions": ["Break West down by product", "Compare to last quarter"],
    "chart_spec": null,
    "clarifying_question": null,
    "tokens": {"prompt": 1300, "completion": 210},
    "cost_usd": 0.0008
  }, "error": null }
```
> P1 returns `chart_spec: null` (charts are P3) and a `clarifying_question: null` (clarify is
> P4). `tokens`/`cost_usd` may be populated in P1 but are surfaced in the UI only from P2.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Unknown dataset (`NOT_FOUND`) |
| 400 | Empty question (`BAD_REQUEST`) |
| 502 | LLM unavailable after retries (`LLM_UNAVAILABLE`) |
| 500 | Agent run failed (`RUN_FAILED`) — `status:"failed"` with `error_message` |

### `POST /ask/stream`  *(Phase 3 — real; Phase 1 STUB)*

Streaming variant of `/ask` (SSE/chunked): emits `plan`, per-iteration `step`, and the final
`answer` events with an elapsed timer. In P1 this route does not exist; the frontend's live-step
UI is a labelled stub.

### `GET /datasets`  *(Phase 2 — real; Phase 1 STUB)*

**Purpose:** list all datasets for the Library. **Response:** `data: [ {dataset summary} ]`.
In P1 the Library UI is a labelled stub; this endpoint lands in P2.

### `GET /datasets/{id}/runs`  *(Phase 2 — real; Phase 1 STUB)*

**Purpose:** per-dataset run history (question, code, result, status, cost, timestamps).
**Response:** `data: [ {run summary} ]`. P2.

### `GET /cost/daily`  *(Phase 2 — real; Phase 1 STUB)*

**Purpose:** running daily token/$ total. **Response:** `data: {date, tokens, cost_usd}`. P2.

### `GET/POST/DELETE /datasets/{id}/notes`  *(Phase 4 — real; STUB earlier)*

**Purpose:** CRUD column notes / business rules. P4.

### `DELETE /datasets/{id}`  *(Phase 2 — real)*

**Purpose:** delete a dataset, its file, and cascading rows. P2.

## Authentication

None. Localhost, single trusted user. No tokens, no sessions.
