# API

> The HTTP contract Phase 1 needs. The frontend builds against this in parallel with the backend. All responses use the existing `ok(data)` / `api_error(code, message, status)` envelope from `src/api/_common.py`: success → `{"data": ..., "error": null}`; failure → HTTP error with `{"detail": {"code": ..., "message": ...}}`.

---

## API Style

REST over JSON, plus one multipart upload endpoint. Served by the existing FastAPI app on port 8001; the Next.js UI calls these from `/app`.

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Upload a CSV or `.xlsx` file. The backend stores it locally, profiles it (schema + row count) **with no LLM call**, and returns the dataset id + detected schema.

**Request:** `multipart/form-data` with a single field `file` (the CSV/xlsx).

**Response:**
```json
{
  "data": {
    "dataset_id": "uuid",
    "filename": "sales_2024.csv",
    "file_type": "csv",
    "row_count": 1240,
    "schema": {
      "columns": [
        {"name": "region", "dtype": "string"},
        {"name": "sales",  "dtype": "number"},
        {"name": "date",   "dtype": "date"}
      ]
    }
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | No file, unsupported type (not csv/xlsx), or unreadable/empty file (`code: BAD_UPLOAD`) |
| 500 | Storage or profiling failure (`code: INTERNAL`) |

---

### `POST /chat`

**Purpose:** Ask a plain-language question about an uploaded dataset. Runs the agent graph (plan → local aggregate → compose) and returns a plain-language answer plus an optional chart spec. Creates a conversation on first call; continues it when `conversation_id` is supplied.

**Request:**
```json
{
  "dataset_id": "uuid",
  "question": "what were total sales by region?",
  "conversation_id": "uuid (optional — omit to start a new conversation)"
}
```
> The frontend sends only `dataset_id`, `question`, and (after the first turn) `conversation_id`. Recent history is reconstructed server-side from the stored `Message` rows for the conversation — the client does not need to send full history. (The agent state's `history` field is populated by the runner from the DB.)

**Response:**
```json
{
  "data": {
    "conversation_id": "uuid",
    "answer": "Total sales were highest in West ($1.2M), then East ($0.9M)…",
    "chart": {
      "type": "bar",
      "title": "Total sales by region",
      "labels": ["West", "East", "North", "South"],
      "series": [{"name": "Sales", "values": [1200000, 900000, 700000, 500000]}]
    }
  },
  "error": null
}
```
- `chart` is `null` when the question warrants no chart (e.g. a single-value answer).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `dataset_id` not found (`code: NOT_FOUND`) |
| 400 | Empty question, or missing referenced file on disk (`code: BAD_REQUEST`) |
| 502 | Gemini call failed (`code: LLM_ERROR`) — Phase 1 surfaces this; Phase 5 adds retry/degrade |
| 500 | Aggregation/internal error (`code: INTERNAL`) |

---

### `GET /datasets/{dataset_id}`

**Purpose:** Fetch a dataset's metadata + schema (for restoring UI state).

**Response:** same `data` shape as the `POST /datasets` response.

| Status | Condition |
|--------|-----------|
| 404 | dataset not found |

---

### `GET /conversations/{conversation_id}`

**Purpose:** Fetch a conversation's full ordered message thread (for restoring the chat on reload — used in earnest in Phase 2, but available in Phase 1).

**Response:**
```json
{
  "data": {
    "conversation_id": "uuid",
    "dataset_id": "uuid",
    "messages": [
      {"role": "user", "content": "what were total sales by region?", "chart": null},
      {"role": "assistant", "content": "Total sales were…", "chart": { "...ChartSpec..." }}
    ]
  },
  "error": null
}
```

| Status | Condition |
|--------|-----------|
| 404 | conversation not found |

---

## Chart Spec

> The exact JSON shape both backend (`compose_answer_and_pick_chart`) and frontend (Recharts renderer) agree on. Returned in `POST /chat` and stored in `Message.chart_json`.

```json
{
  "type": "bar | line | pie",
  "title": "string",
  "labels": ["string", ...],
  "series": [
    {"name": "string", "values": [number, ...]}
  ]
}
```
- `bar` → comparison across categories; `line` → trend over an ordered axis (e.g. dates/months); `pie` → distribution/share (single series).
- `labels.length` equals each `series[*].values.length`.
- A pie chart uses exactly one series. Bar/line may have one or more series.
- `chart` is `null` when no chart is appropriate (single-value answers).

## Authentication

None — single local user on `localhost`. No auth tokens in Phase 1.
