# API

> FastAPI, single-origin on `http://localhost:8001`. All JSON responses use the skeleton envelope `{"data": ..., "error": null}` (`src/api/_common.py`); errors raise `api_error(code, message, status)` → `{"detail": {"code", "message"}}`. No auth (single local user). Routes extend the skeleton's `src/api/` package; the static frontend is mounted at `/app`.

---

## Phase 1 endpoints (real)

### `POST /datasets` — upload a CSV
Multipart upload. Saves the file to `data/uploads/<id>.csv`, extracts schema + sample rows, counts rows/columns, creates a `datasets` row.
- **Request:** `multipart/form-data`, field `file` (CSV; simple `.xlsx` in P4).
- **Response:** `{ data: { id, filename, row_count, column_count, schema: [{name,type}], sample_rows: [...] } }`
- **Errors:** `UNSUPPORTED_FORMAT` (415), `FILE_TOO_LARGE` (413, > ~100MB), `PARSE_ERROR` (422).

### `POST /questions` — ask a question
Runs the plan-then-execute agent against the real Gemini Flash model and persists the result. Synchronous (target < 30s); step updates are surfaced via the polled payload (see streaming note).
- **Request:** `{ dataset_id: str, text: str }`
- **Response:** `{ data: { id, status, answer, key_numbers, result_table, plan, steps: [{step_index, language, code, result, error, latency_ms}], cost: { tokens_in, tokens_out, estimated_usd }, cost_guard_warning } }`
- **Errors:** `DATASET_NOT_FOUND` (404), `ANALYSIS_FAILED` (200 with `status:"failed"` + `error_message` — surfaced, not thrown, so the UI shows what it tried).

### `GET /questions/{id}` — fetch a question's full answer payload
Same shape as the `POST /questions` response. Used for polling while `status:"pending"` (live step updates) and to re-open a past answer.
- **Errors:** `NOT_FOUND` (404).

> **Streaming note (Phase 1):** answers stream as **step updates**, not LLM tokens. The frontend polls `GET /questions/{id}` (or a `GET /questions/{id}/events` SSE endpoint if added) while `pending`, rendering `steps` as they are persisted. Token-by-token streaming is out of scope (see [`roadmap.md`](roadmap.md#what-this-agent-does-not-do-out-of-scope)).

## Later-phase endpoints (stubbed/labelled in Phase 1, real in the noted phase)

| Endpoint | Method | Phase | Purpose |
|----------|--------|-------|---------|
| `/datasets/{id}/profile` | GET | 2 | Auto-profile (per-column types, ranges, nulls, quality flags). |
| (`followups` in question payload) | — | 2 | 2–3 suggested follow-ups returned with the answer. |
| (`chart_spec` in question payload) | — | 3 | Interactive chart spec + bounded chart data. |
| `/datasets` | GET | 4 | List the library. |
| `/datasets/{id}` | DELETE | 4 | Remove a dataset + its file. |
| `/history` | GET | 4 | Browsable question+answer history. |
| `/conversations` / `/conversations/{id}` | GET | 4 | Durable threads + memory. |
| `/cost/daily` | GET | 4 | Running daily cost total. |

> In Phase 1 the later endpoints are not implemented; the UI surfaces for them are labelled non-functional stubs (see [`ui.md`](ui.md)). They are added in their phase, never called by the Phase 1 frontend.

## Health

`GET /health` — skeleton route, returns `{ data: { status: "ok" } }`.
