# Data Model

> SQLite (production driver here IS SQLite) via SQLAlchemy 2.0 + Alembic. Extends the skeleton's `src/db/models.py` (which currently has `Base` + `RunRow`). The `runs` table is superseded by `questions`; `RunRow` may be kept or removed by the migration. All ids are UUID strings; all timestamps are timezone-aware UTC. **Raw data rows are never stored in the DB** — only the local file path, schema, bounded sample rows, bounded step results, and aggregates. The full CSV lives only on disk (`data/uploads/`).

---

## Entities

### `datasets` — the file library (Phase 1; library management UI in Phase 4)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `filename` | str | original upload name |
| `path` | str | local path `data/uploads/<id>.<ext>` |
| `format` | str | `csv` \| `xlsx` (xlsx in P4) |
| `row_count` | int | counted at upload (DuckDB) |
| `column_count` | int | |
| `schema_json` | JSON | `[{name, type}]` — inferred column schema |
| `sample_rows_json` | JSON | ≤ `AGENT_SAMPLE_ROWS` rows (the only stored rows) |
| `created_at` | timestamp | |

### `questions` — one asked question + its answer (Phase 1)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `dataset_id` | str FK→datasets | nullable in P4 multi-file (see `question_datasets`) |
| `conversation_id` | str FK→conversations | nullable; set in P4 |
| `text` | str | the user's plain-language question |
| `status` | str | `pending` \| `completed` \| `failed` |
| `plan_json` | JSON | ordered plan steps (text) |
| `answer` | str \| null | plain-language answer |
| `key_numbers_json` | JSON \| null | `[{label, value}]` |
| `result_table_json` | JSON \| null | `{columns, rows}` (bounded) |
| `chart_spec_json` | JSON \| null | Phase 3 |
| `followups_json` | JSON \| null | Phase 2 |
| `cost_guard_warning` | str \| null | set when the step cap was hit |
| `error_message` | str \| null | |
| `created_at` | timestamp | |

### `analysis_steps` — per-step audit trail (code + result) (Phase 1)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `question_id` | str FK→questions | |
| `step_index` | int | 0-based order |
| `language` | str | `sql` \| `pandas` |
| `code` | str | the generated code that ran locally |
| `result_json` | JSON \| null | bounded aggregate result (≤ `AGENT_MAX_RESULT_ROWS`) |
| `error` | str \| null | code/execution error if any |
| `latency_ms` | int | step execution time |
| `created_at` | timestamp | |

### `cost_records` — per-question cost (Phase 1; daily total aggregation in Phase 4)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `question_id` | str FK→questions | |
| `tokens_in` | int | summed across all LLM nodes |
| `tokens_out` | int | |
| `estimated_usd` | float | tokens × Flash price (settings) |
| `model` | str | the model id used |
| `created_at` | timestamp | indexed for daily-total queries |

### `dataset_profiles` — auto-profile on upload (Phase 2)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `dataset_id` | str FK→datasets | |
| `profile_json` | JSON | per-column: type, min/max/range, null_count, distinct_count, quality_flags |
| `created_at` | timestamp | |

### `conversations` — durable chat threads + memory (Phase 4)

| Field | Type | Notes |
|-------|------|-------|
| `id` | str PK | UUID |
| `title` | str | derived from first question |
| `created_at` / `updated_at` | timestamp | |

### `question_datasets` — multi-file join link (Phase 4)

| Field | Type | Notes |
|-------|------|-------|
| `question_id` | str FK→questions | composite PK |
| `dataset_id` | str FK→datasets | composite PK |

## Relationships

```
conversations 1───* questions *───1 datasets            (P1: questions→datasets one-to-one)
questions 1───* analysis_steps                          (audit trail: code + result per step)
questions 1───1 cost_records                            (per-question cost)
datasets 1───1 dataset_profiles                         (P2)
questions *───* datasets  via question_datasets         (P4 multi-file)
```

## Lifecycle

1. **Upload** → `datasets` row created; CSV written to disk; schema + sample rows extracted and stored. (P2: `dataset_profiles` computed.)
2. **Ask** → `questions` row (`pending`); agent runs.
3. **Per step** → `analysis_steps` row (code + bounded result) appended.
4. **Finalize** → `questions` updated (`completed`/`failed`, answer, plan, table, warning); `cost_records` written.
5. **History** (P4) → questions/steps/cost rows are read-only audit records, browsable forever; `cost_records.created_at` powers the daily total. Conversations group questions across days; `messages` for memory are reconstructed from a conversation's prior questions+answers.
6. **Delete dataset** (P4) → removes the `datasets` row + file; its questions remain as history (referential rows nulled/retained per delete policy).

## Phase Mapping

| Table | Phase |
|-------|-------|
| `datasets`, `questions`, `analysis_steps`, `cost_records` | Phase 1 |
| `dataset_profiles` | Phase 2 |
| (`chart_spec_json` populated) | Phase 3 |
| `conversations`, `question_datasets` | Phase 4 |
