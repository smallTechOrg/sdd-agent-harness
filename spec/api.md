# API

---

## API Style

REST + Server-Sent Events (SSE) for live step streaming. FastAPI, port 8001. Responses use the skeleton's `ok(...)` envelope (`{data: ...}`) and `api_error(...)` shape. The frontend is served at `/app`; API routes are at the root.

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Upload one CSV/Excel file; store it, load it into a server-side DataFrame, auto-profile it.

**Request:** `multipart/form-data` with `file` (the upload) and optional `name`.

**Response:**
```json
{ "data": {
  "dataset_id": "uuid",
  "name": "sales.csv",
  "row_count": 240000,
  "col_count": 12,
  "profile": { "columns": [ { "name": "region", "dtype": "object", "n_unique": 5, "n_null": 0 } ],
               "ranges": { "amount": { "min": 0.0, "max": 9912.5 } },
               "quality_flags": [ "column 'date' has 312 unparseable values" ] }
} }
```
Profile contains schema/dtypes/ranges/quality flags ONLY — never raw rows.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Not a CSV/Excel, malformed, or > size limit (~100MB) |
| 500 | Profiling/load failure |

### `POST /datasets/{dataset_id}/ask` (SSE)

**Purpose:** Ask a plain-language question; stream the agent's live steps, then the final answer.

**Request:**
```json
{ "question": "What were total sales by region?" }
```
Conversation memory: the server seeds prior turns for this dataset/session, so follow-ups understand context.

**Response:** `text/event-stream`. Event sequence:
```
event: run_started   data: {"run_id":"uuid","max_steps":6}
event: step          data: {"step_index":1,"total":6,"node":"plan","status":"worked","detail":"strategy: group by region, sum amount"}
event: step          data: {"step_index":2,"total":6,"node":"generate_code","status":"worked","code":"result = df.groupby('region')['amount'].sum()"}
event: step          data: {"step_index":3,"total":6,"node":"execute","status":"worked","result_summary":"5 rows"}
event: step          data: {"step_index":4,"total":6,"node":"inspect","status":"worked","detail":"finish"}
event: answer        data: {"prose":"...","chart":{...},"table":{...},"code":"...","tokens":{"prompt":820,"completion":140},"cost_usd":0.0003,"daily_total_usd":0.012,"uncertainty":null}
event: done          data: {"run_id":"uuid","status":"completed"}
```
A `needs_clarification` run streams an `answer` event whose payload carries `clarifying_question` and `status:"needs_clarification"`. On failure: `event: error  data: {"message":"..."}`.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | dataset_id unknown |
| 400 | empty question |
| 500 (or `error` event) | LLM/exec fatal failure after retries |

### `GET /datasets/{dataset_id}/runs`

**Purpose:** Per-dataset audit history (browsable list of past runs).

**Response:**
```json
{ "data": { "runs": [ { "run_id":"uuid","question":"...","status":"completed",
  "step_count":4,"cost_usd":0.0003,"created_at":"..." } ] } }
```

### `GET /runs/{run_id}`

**Purpose:** Full detail of one run for the audit drawer — plan, every step, final code, prose, chart, table, tokens, cost.

**Response:** `{ "data": { run fields + "steps": [ RunStep... ] } }`

### `GET /usage/today`

**Purpose:** Running daily cost/token total for the cost meter.

**Response:** `{ "data": { "date":"2026-06-28","total_cost_usd":0.012,"total_tokens":18400,"run_count":9 } }`

### Phase 2/3 endpoints (stubbed in Phase 1)
- `GET /datasets` — list the persistent library (Phase 2).
- `PATCH /datasets/{id}` / `DELETE /datasets/{id}` — rename/delete (Phase 2).
- `POST /datasets/{id}/files` + `POST /datasets/{id}/joins` — add files / configure joins (Phase 3).

## Authentication

None — single local user on localhost. No auth, no multi-tenant scoping.
