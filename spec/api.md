# API

---

## API Style

REST (JSON), FastAPI, single origin with the UI at `/app/`. Single user, **no authentication**. Responses use the skeleton envelope `{"data": ..., "error": null}`; errors raise `HTTPException` with `{"code", "message"}`.

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Upload a CSV. Parsed and stored locally; returns a `dataset_id` and the detected schema. See [upload_dataset.md](capabilities/upload_dataset.md).

**Request:** `multipart/form-data` with a single `file` field (`.csv`).

**Response:**
```json
{
  "data": {
    "dataset_id": "uuid",
    "filename": "sales.csv",
    "row_count": 1043,
    "schema": [
      {"name": "region", "dtype": "object", "friendly_dtype": "text"},
      {"name": "revenue", "dtype": "float64", "friendly_dtype": "decimal"}
    ]
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | File is not parseable as CSV, or exceeds `AGENT_MAX_UPLOAD_MB` |
| 500 | Disk write or DB insert failure |

### `POST /datasets/{dataset_id}/ask`

**Purpose:** Ask one plain-English question about a dataset; returns a plain-English answer computed from a LOCAL profile (raw rows never sent to Gemini). See [answer_question.md](capabilities/answer_question.md).

**Request:**
```json
{ "question": "What is the average revenue per region?" }
```

**Response:**
```json
{
  "data": {
    "run_id": "uuid",
    "dataset_id": "uuid",
    "status": "completed",
    "answer": "Average revenue is highest in the West region at …",
    "error": null
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 200 + `status:"failed"` | Unknown `dataset_id`, unreadable file, or Gemini failure → human-readable `answer`/`error` (graceful, not a crash) |
| 400 | Empty/missing `question` |

### Deferred endpoints (Phase 2/3 — UI stubs in Phase 1)

- `POST /datasets/{dataset_id}/chart` — [visual_summary.md](capabilities/visual_summary.md) (Phase 2)
- `POST /datasets/{dataset_id}/insights` — [detect_anomalies.md](capabilities/detect_anomalies.md) (Phase 3)

### Skeleton endpoints retained

- `GET /health` — liveness (skeleton).
- `GET /runs/{run_id}`, `POST /runs` — kept from the skeleton; the CSV UI uses the dataset endpoints above.

## Authentication

None. Local single-user tool bound to localhost; not exposed to a network.
