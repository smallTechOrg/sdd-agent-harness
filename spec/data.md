# Data Model

---

## Storage Technology

SQLite + SQLAlchemy 2.0 (single local user, audit history only — no concurrent-writer or scale needs). Uploaded files are persisted in a local managed file store (`AGENT_DATASET_STORE_DIR`, default `data/datasets/`); the database holds metadata and audit rows, never raw cell values. Extends the skeleton's `src/db/models.py` (`RunRow` is renamed/extended; two new tables added).

## Entities

### Entity: Dataset

A single uploaded file, profiled and (from Phase 2) persisted across sessions.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| name | TEXT | yes | User-facing name (defaults to filename) |
| file_path | TEXT | yes | Path in the managed store (raw file lives here, never in LLM) |
| row_count | INTEGER | yes | Rows in the file |
| col_count | INTEGER | yes | Columns in the file |
| profile_json | TEXT (JSON) | yes | Schema, dtypes, ranges, quality flags — NO raw rows |
| size_bytes | INTEGER | yes | File size |
| created_at | TIMESTAMP | yes | Upload time |
| updated_at | TIMESTAMP | yes | Last touched |

### Entity: Run

One question-and-answer cycle against a dataset (the audit unit).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| dataset_id | TEXT (FK → Dataset.id) | yes | Which dataset was queried |
| question | TEXT | yes | The plain-language question |
| status | TEXT | yes | pending / completed / failed / needs_clarification |
| plan | TEXT | no | The strategy the agent chose |
| final_code | TEXT | no | The exact pandas code that produced the answer |
| prose | TEXT | no | The prose answer |
| chart_json | TEXT (JSON) | no | Chart spec rendered by the frontend |
| table_json | TEXT (JSON) | no | Results table (aggregate result only) |
| prompt_tokens | INTEGER | no | Cumulative prompt tokens |
| completion_tokens | INTEGER | no | Cumulative completion tokens |
| cost_usd | REAL | no | Estimated cost for this run |
| step_count | INTEGER | no | How many loop iterations were used |
| error_message | TEXT | no | Set when status=failed |
| created_at | TIMESTAMP | yes | Question asked |
| completed_at | TIMESTAMP | no | Answer finished |

### Entity: RunStep

One node execution within a run — the per-step audit trail and what the SSE stream replays.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| run_id | TEXT (FK → Run.id) | yes | Parent run |
| step_index | INTEGER | yes | Order (drives the "Step N of M" counter) |
| node | TEXT | yes | plan / generate_code / execute / inspect / finalize / clarify |
| status | TEXT | yes | tried / failed / worked |
| code | TEXT | no | Code generated/run at this step (if any) |
| result_summary | TEXT | no | Aggregate summary of the step's result (NO raw rows) |
| detail | TEXT | no | Human-readable note (plan text, inspect decision, error) |
| latency_ms | INTEGER | no | Step latency |
| created_at | TIMESTAMP | yes | Step time |

### Relationships

- `Dataset 1───* Run` (a dataset has many runs; history is browsed per-dataset).
- `Run 1───* RunStep` (a run has many ordered steps).
- Deleting a Dataset cascades to its Runs and their RunSteps, and removes the stored file.

## Data Lifecycle

- **Create:** Dataset on upload; Run on each question; RunStep per node execution (streamed live + persisted).
- **Update:** Run gains `prose`/`chart`/`code`/`tokens`/`cost`/`status` as it completes; Dataset `updated_at` on each new run (Phase 2 library ordering).
- **Delete:** Phase 1 — datasets are session-scoped (DataFrame cache cleared on restart; rows may remain but file store is ephemeral). Phase 2 — explicit user delete of a dataset cascades.
- Nothing is auto-archived; the single user manages their own library.

## Sensitive Data

The uploaded file may contain PII. The hard boundary: **raw rows live only in the local file store and the in-memory DataFrame — never in the database as cell values, and never in any LLM payload.** `profile_json`, `result_summary`, `table_json` contain only schema and computed aggregates. The privacy gate (`src/llm/payload.py`) is the enforced choke point; `test_privacy_boundary` asserts no raw cell value appears in any outbound LLM request.
