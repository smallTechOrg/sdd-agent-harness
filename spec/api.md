# API

> REST over FastAPI, single origin `http://localhost:8001`. Frontend served at `/app/`. All responses use the skeleton envelope: success → `{"data": <payload>, "error": null}` via `ok(data)`; failure → HTTP error with `{"detail": {"code": ..., "message": ...}}` via `api_error(code, message, status)`.

---

## API Style

REST. Phase-1 endpoints below, then the Phase-2 dataset-browser endpoints. Later phases add compare/notes/cost endpoints (see `roadmap.md`).

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Upload a CSV; ingest into local DuckDB and profile it. No LLM call.

**Request:** `multipart/form-data` with a `file` field (a `.csv`). (Excel rejected in Phase 1 with a clear message — stub.)

**Response (200):**
```json
{
  "data": {
    "id": "uuid",
    "name": "sales.csv",
    "row_count": 124000,
    "columns": [{"name": "region", "type": "VARCHAR"}, {"name": "sales", "type": "DOUBLE"}],
    "profile": {
      "row_count": 124000,
      "columns": [
        {"name": "region", "type": "VARCHAR", "nulls": 0, "distinct": 5},
        {"name": "sales", "type": "DOUBLE", "nulls": 12, "min": 0.0, "max": 98000.0}
      ]
    },
    "status": "ready"
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | `BAD_FILE` — not a `.csv`, empty, or unparseable |
| 413 | `FILE_TOO_LARGE` — over the ~100MB cap |
| 500 | `INGEST_FAILED` — DuckDB ingest error (message includes the reason) |

### `GET /datasets/{id}`

**Purpose:** Fetch a dataset's profile (re-open the profile card).

**Response (200):** same `data` shape as `POST /datasets` (id, name, row_count, columns, profile, status).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `NOT_FOUND` — no such dataset |

### `POST /datasets/{id}/ask`

**Purpose:** Ask a natural-language question; run the agent (plan → DuckDB SQL → execute local → phrase) and return the answer + chart + summary table + the show-its-work trace.

**Request:**
```json
{ "question": "Which region had the highest total sales?" }
```

**Response (200, completed):**
```json
{
  "data": {
    "run_id": "uuid",
    "status": "completed",
    "answer": "The West region had the highest total sales at $4.2M.",
    "key_numbers": [{"label": "West total sales", "value": "$4.2M"}],
    "chart": {"type": "bar", "x": "region", "y": "total_sales",
              "data": [{"region": "West", "total_sales": 4200000}, {"region": "East", "total_sales": 3100000}]},
    "table": {"columns": ["region", "total_sales"],
              "rows": [["West", 4200000], ["East", 3100000]]},
    "plan": "Sum sales grouped by region, order descending, take the top.",
    "sql": "SELECT region, SUM(sales) AS total_sales FROM t GROUP BY region ORDER BY total_sales DESC",
    "trace": [
      {"step": "plan", "ok": true, "latency_ms": 820},
      {"step": "execute", "ok": true, "latency_ms": 140},
      {"step": "phrase", "ok": true, "latency_ms": 610}
    ],
    "cost_usd": 0.0021
  },
  "error": null
}
```

A trace with a recovered SQL error looks like:
```json
"trace": [
  {"step": "plan", "ok": true},
  {"step": "execute", "ok": false, "error": "Catalog Error: Scalar Function with name julianday does not exist"},
  {"step": "retry", "ok": true, "sql": "... date_diff('day', ...) ..."},
  {"step": "execute", "ok": true},
  {"step": "phrase", "ok": true}
]
```

**Response (200, failed):** `status="failed"`, `answer`/`chart`/`table` null, `error_message` set, `trace` still present (shows what was tried). The HTTP status is 200 — the failure is in the body so the UI can render the trace (mirrors the skeleton's "error in body, never swallowed" contract).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `NOT_FOUND` — no such dataset |
| 422 | `EMPTY_QUESTION` — blank question |
| 200 (body) | agent failure (LLM down, or SQL uncorrectable after retries) → `status="failed"`, `error_message` |

---

## Phase 2 — Dataset browser endpoints

> Two read-only endpoints powering the persistent dataset browser. Both are **pure DB reads — no LLM call** — so listing datasets and re-opening past runs is free and never sends any data off-machine. Re-opening a past run renders from the **persisted bounded record**, exactly as the live `ask` did, so it is rendered by the *same* `AnswerPanel` with no new render component.

### `GET /datasets`

**Purpose:** List all datasets for the sidebar, newest first. Powers the real switchable "Past datasets" list (replacing the Phase-1 stub). No LLM call.

**Response data:** an array of **lightweight summaries** — NOT the full profile. The UI fetches the full profile via the existing `GET /datasets/{id}` only when a dataset is selected.

**Response (200):**
```json
{
  "data": [
    {"id": "uuid-2", "name": "headcount.csv", "row_count": 480, "status": "ready", "question_count": 2, "created_at": "2026-06-29T14:02:00Z"},
    {"id": "uuid-1", "name": "sales.csv", "row_count": 124000, "status": "ready", "question_count": 5, "created_at": "2026-06-29T13:40:00Z"}
  ],
  "error": null
}
```

Ordering: newest first by `Dataset.created_at` descending. Empty case: `{"data": [], "error": null}` (no error — an empty list is a valid state the sidebar renders as "No past datasets yet").

> **Assumed:** each summary includes `question_count` — a cheap `COUNT(question_runs)` per dataset (single grouped query, no N+1). It is useful in the sidebar (shows how much history a dataset has) and costs nothing meaningful. If the COUNT is ever undesirable it can be dropped without changing the other fields. `status` is included so a `failed`-ingest dataset can be shown distinctly.

**Error cases:** none beyond transport — always returns 200 with an array (possibly empty).

### `GET /datasets/{id}/runs`

**Purpose:** The question/run history for one dataset, newest first. Powers the run-history list and the re-open-a-past-run interaction. **No LLM call — pure DB read.** Re-opening history is free and private: the answer + chart + table are reconstructed from the persisted `QuestionRun` record, and **no raw row is ever read or sent anywhere** (the persisted `result_json` is already the bounded summary).

**Response data:** an array of run records. **Each record carries the SAME shape the live `POST /datasets/{id}/ask` returns** (the `AskResult`), so the frontend renders a re-opened run through the existing `AnswerPanel`/`Chart`/`SummaryTable`/`ShowItsWork` with no new component. The backend reconstructs `chart.data` and `table` from the persisted record **exactly as the runner's `_ask_payload` / `_chart_data` do for a live ask** — `table` from `result_json` (`{columns, rows}`), and `chart.data` rebuilt by zipping the persisted `chart` spec's `x`/`y` against `result_json`'s rows. A re-opened run therefore renders pixel-identically to when it was first answered.

**Response (200):**
```json
{
  "data": [
    {
      "run_id": "run-uuid-2",
      "status": "completed",
      "question": "Which region had the highest total sales?",
      "answer": "The West region had the highest total sales at $4.2M.",
      "key_numbers": [{"label": "West total sales", "value": "$4.2M"}],
      "chart": {"type": "bar", "x": "region", "y": "total_sales",
                "data": [{"region": "West", "total_sales": 4200000}, {"region": "East", "total_sales": 3100000}]},
      "table": {"columns": ["region", "total_sales"],
                "rows": [["West", 4200000], ["East", 3100000]]},
      "plan": "Sum sales grouped by region, order descending, take the top.",
      "sql": "SELECT region, SUM(sales) AS total_sales FROM t GROUP BY region ORDER BY total_sales DESC",
      "trace": [
        {"step": "plan", "ok": true, "latency_ms": 820},
        {"step": "execute", "ok": true, "latency_ms": 140},
        {"step": "phrase", "ok": true, "latency_ms": 610}
      ],
      "cost_usd": 0.0021,
      "error_message": null,
      "created_at": "2026-06-29T13:55:00Z"
    }
  ],
  "error": null
}
```

This is the live `ask` payload plus two fields that history needs: **`question`** (so the history list can label each run) and **`created_at`** (so the list can order/timestamp). A `failed` run is included with `status="failed"`, `answer`/`chart`/`table` null, `error_message` set, and `trace` present — so the user can re-open a failed run and still see what was tried (mirrors the live failed-ask body).

Ordering: newest first by `QuestionRun.created_at` descending. Empty-history case: `{"data": [], "error": null}` (a dataset with no questions yet renders an empty history panel, not an error).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `NOT_FOUND` — no such dataset (distinct from an existing dataset with empty history, which is `200` + `[]`) |

### `GET /datasets/{id}` (existing, Phase 1) — used to re-load a selection

When the user clicks a dataset in the sidebar, the UI calls the **existing** `GET /datasets/{id}` to re-load that dataset's full profile (the profile card), then calls `GET /datasets/{id}/runs` for its history. No new endpoint is needed for switching — `GET /datasets/{id}` already returns the full profile shape.

## Authentication

None — single local user, localhost only.
