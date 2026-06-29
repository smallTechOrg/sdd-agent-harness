# API

---

## API Style

REST (FastAPI, `api:app` on port 8001). All responses use the skeleton envelope `{"data": ..., "error": null}` (see `src/api/_common.py`); errors raise `HTTPException` with `detail = {code, message}`. The frontend reads `data` / `detail.message`.

> The existing `/runs` endpoints from the skeleton are superseded by the dataset/ask endpoints below for the analysis path. `GET /health` is retained.

## Endpoints / Commands

### `POST /datasets`  (Phase 1)

**Purpose:** Upload a CSV; ingest it into a local DuckDB file; return the dataset summary.

**Request:** `multipart/form-data` with a `file` field (CSV; Excel added Phase 3).

**Response:**
```json
{
  "data": {
    "id": "uuid",
    "name": "sales.csv",
    "row_count": 12345,
    "schema": [{ "name": "revenue", "type": "DOUBLE" }, { "name": "region", "type": "VARCHAR" }],
    "profile": [
      {
        "column": "revenue",
        "type": "DOUBLE",
        "null_count": 0,
        "distinct_count": 12,
        "min": 120.0,
        "max": 660.0,
        "flags": []
      },
      {
        "column": "region",
        "type": "VARCHAR",
        "null_count": 0,
        "distinct_count": 4,
        "min": null,
        "max": null,
        "flags": []
      }
    ]
  },
  "error": null
}
```

**`profile` — Phase 2, now populated.** A list with one entry per column, computed
entirely in local DuckDB (aggregate-only — no raw rows). Each entry:

| Field | Type | Notes |
|-------|------|-------|
| `column` | string | column name |
| `type` | string | DuckDB column type |
| `null_count` | int \| null | number of null values |
| `distinct_count` | int \| null | number of distinct values |
| `min` | number/string \| null | minimum — populated for **numeric** columns only, else `null` |
| `max` | number/string \| null | maximum — numeric columns only, else `null` |
| `flags` | string[] | data-quality flags: any of `all_null`, `constant`, `high_null` (and `error` if a per-column stat failed) |

Profiling is non-fatal: a per-column failure yields a partial entry (`flags: ["error"]`) and never blocks the upload. `profile` is `null` only if no column could be profiled.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Not a CSV / unparseable / empty file |
| 413 | File exceeds the ~100MB limit |
| 500 | Ingest/DuckDB failure |

### `POST /datasets/{id}/ask`  (Phase 1) — **the core contract both Phase-1 slices build to**

**Purpose:** Ask one plain-English question about a dataset; run the agent; return the answer with the exact SQL.

**Request:**
```json
{ "question": "What is the total revenue?" }
```

**Response (success):**
```json
{
  "data": {
    "run_id": "uuid",
    "dataset_id": "uuid",
    "status": "completed",
    "question": "What is the total revenue?",
    "answer": "Total revenue across all rows is 4,210,500.",
    "sql": "SELECT sum(revenue) AS total_revenue FROM data;",
    "result": [{ "total_revenue": 4210500 }],
    "flagged": false,
    "error": null,

    "chart": {
      "type": "bar",
      "x": "region",
      "y": "total_revenue",
      "series": null,
      "title": "What is total revenue by region?"
    },
    "summary_table": {
      "columns": [
        { "name": "region", "type": "text", "align": "left" },
        { "name": "total_revenue", "type": "number", "align": "right" }
      ],
      "rows": [
        ["North", 1210.0],
        ["South", 665.0]
      ]
    },
    "followups": [
      "How does revenue trend month over month?",
      "Which product drives the most revenue in each region?"
    ],
    "tokens": null
  },
  "error": null
}
```

**Phase-2 fields — now populated** (each is `null` when not applicable, ambiguous, or on a failed run — never fabricated):

- **`chart`** — a chart spec derived deterministically from the **aggregate result shape only** (no raw rows, no LLM), or `null` when not chartable (single scalar, ambiguous shape).
  - `type`: `"bar"` | `"line"` | `"scatter"`
  - `x`: result column for the x-axis (the label/dimension, or first numeric for scatter)
  - `y`: result column for the y-axis (the numeric measure)
  - `series`: optional second categorical column for grouping, else `null`
  - `title`: short title (derived from the question)
  - Rules: single scalar → `null`; one label + one numeric → `bar` (or `line` if the label is temporal/date-like); two numerics → `scatter`.
- **`summary_table`** — a formatted table over the aggregate result (deterministic, no LLM), or `null` for an empty result.
  - `columns`: `[{ "name", "type": "number"|"text", "align": "right"|"left" }]` — numeric columns are right-aligned.
  - `rows`: `[[...], ...]` row-major cell values; floats are rounded **for display only** (≤4 dp) and never altered in a way that changes correctness.
- **`followups`** — `["q1", "q2", "q3"]`, 2–3 short follow-up questions from Gemini grounded in the **schema + aggregate result only** (never raw rows), or `null` (non-fatal: a follow-up failure never fails the run).
- **`tokens`** — stays `null` until Phase 3.

**Response contract notes (binding for both slices):**
- Phase 1 ALWAYS returns `answer`, `sql`, `result` on success. As of Phase 2, `chart`, `summary_table`, `followups` are populated for real (each `null` when not applicable); `tokens` remains a `null` placeholder until Phase 3.
- `flagged: true` when the agent returns a best-guess (ambiguous question) rather than a confident answer — the UI shows a "best-guess" badge.
- On failure (`status: "failed"`): `answer`/`sql`/`result` are `null` and `error` carries the reason. `chart`/`summary_table`/`followups` are ALSO `null` on a failed run — enrichment is never fabricated. The agent NEVER returns a fabricated number — a failure is surfaced, not hidden.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Empty question |
| 404 | Unknown dataset id |
| 500 | Unexpected internal error (Gemini/infra). SQL errors are retried internally and do not 500 unless retries are exhausted, which returns `200` with `status:"failed"`. |

### `GET /datasets/{id}/runs`  (Phase 3)

**Purpose:** List past runs (audit trail) for a dataset: question, SQL, result, tokens, timestamp.

### `POST /datasets/{id}/ask/stream`  (Phase 3)

**Purpose:** Server-Sent Events stream of agent steps (generate SQL → execute → answer) for live transparency.

### `GET /health`  (existing)

Liveness check; returns `{ "data": { "status": "ok" }, "error": null }`.

## Authentication

None — single-user, local-only. The app binds to localhost; there is no auth layer by design (`roadmap.md` out-of-scope).
