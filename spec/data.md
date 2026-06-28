# Data Model

> App state for the Personal Data Analysis Agent. Two storage systems (see `architecture.md`): **SQLite via SQLAlchemy** for app state (this file), and **DuckDB + parquet on disk** for the full analysis data (never in SQLite, never sent to the LLM).

---

## Storage Technology

- **SQLite (SQLAlchemy 2.0)** — `sqlite:///./data/agent.db`, migrated by Alembic. All entities below. Small, transactional rows.
- **DuckDB** — `data/analysis.duckdb`; one table `ds_{dataset_id}` per dataset (and Phase-4 derived tables). The analysis compute engine; rebuildable from parquet. Not modelled in SQLAlchemy.
- **Filesystem under `data/`** — `uploads/{dataset_id}.{ext}` (original file), `parquet/{dataset_id}.parquet` (columnar copy for fast re-reads), `exports/` (Phase 4).

**Phase legend:** ✅ written in Phase 1 · 🔵 schema-stub in Phase 1, activated later (phase noted).

---

## Entities

### Entity: Dataset ✅
A loaded file available for analysis.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | Original filename |
| storage_path | str | yes | `data/uploads/...` path |
| parquet_path | str | yes | `data/parquet/...` path |
| duckdb_table | str | yes | `ds_{id}` |
| schema_json | JSON | yes | `[{name, dtype}]` |
| sample_json | JSON | yes | ≤20 sample rows (the LLM-visible sample) |
| row_count | int | yes | Total rows in the full dataset |
| profile_json | JSON | no | 🔵 Phase 2: full column profile (ranges, missing, cardinality) |
| session_id | str | no | 🔵 Phase 2: owning session |
| created_at | timestamp | yes | |

### Entity: Run (Analysis) ✅
One question→answer execution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | FK → Dataset |
| session_id | str | no | 🔵 Phase 2: FK → Session |
| question | str | yes | User's plain-language question |
| code | str | no | Exact generated pandas/SQL (shown in code panel) |
| result_json | JSON | no | Small summary table {columns, rows} |
| key_numbers_json | JSON | no | Headline numbers |
| chart_spec_json | JSON | no | Plotly figure spec |
| answer | str | no | Plain-language prose |
| llm_payload_json | JSON | yes | Exact context sent to the LLM (transparency panel) |
| tokens_in | int | yes | Prompt tokens (summed across nodes) |
| tokens_out | int | yes | Completion tokens |
| cost_estimate | float | yes | USD estimate |
| stage | str | yes | planning/coding/running/charting/done |
| status | str | yes | running/completed/failed |
| flagged | bool | yes | best-guess after exhausting revisions |
| error_message | str | no | On failure |
| revisions | int | yes | Revise-loop count |
| started_at | timestamp | yes | |
| completed_at | timestamp | no | |

> Note: the skeleton's existing `runs` table (`RunRow` with input_text/output_text) is REPLACED in place by this richer schema via an Alembic migration in Phase 1.

### Entity: Session 🔵 (Phase 2)
A persistent workspace the user returns to.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | User/auto label |
| created_at | timestamp | yes | |
| last_active_at | timestamp | yes | |

### Entity: ConversationTurn 🔵 (Phase 2)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| session_id | str | yes | FK → Session |
| role | str | yes | user/assistant |
| content | str | yes | Turn text |
| run_id | str | no | FK → Run (assistant turns) |
| created_at | timestamp | yes | |

### Entity: CostLog 🔵 (Phase 3)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| run_id | str | yes | FK → Run |
| day | date | yes | For daily rollup |
| tokens_in | int | yes | |
| tokens_out | int | yes | |
| cost_estimate | float | yes | |
| created_at | timestamp | yes | |

### Entity: ColumnNote 🔵 (Phase 3)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | FK → Dataset |
| column | str | no | Null = dataset-level business rule |
| note | str | yes | e.g. "revenue excludes refunds" |
| created_at | timestamp | yes | |

### Entity: SavedDataset 🔵 (Phase 4)
A derived result saved as a reusable source.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | User label |
| source_run_id | str | yes | FK → Run that produced it |
| duckdb_table | str | yes | Derived DuckDB table name |
| parquet_path | str | yes | Persisted derived data |
| schema_json | JSON | yes | |
| created_at | timestamp | yes | |

### Entity: AnalysisLibraryEntry 🔵 (Phase 4)
> **Assumed:** the analysis library is a thin view over `runs` (saved/starred runs) rather than a separate copy of question+code+result — avoids duplicating data. This entity is just a star/label on a Run.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| run_id | str | yes | FK → Run |
| label | str | no | User label |
| created_at | timestamp | yes | |

### Relationships
- Dataset 1—N Run; Dataset 1—N ColumnNote; Dataset N—1 Session (Phase 2).
- Session 1—N ConversationTurn; Session 1—N Dataset (Phase 2).
- Run 1—1 CostLog (Phase 3); Run 1—0/1 SavedDataset; Run 1—0/1 AnalysisLibraryEntry (Phase 4).

## Data Lifecycle

- **Dataset:** created on upload (file → uploads + parquet + DuckDB table + row); persists until the user deletes it. Phase 1 keeps all uploads.
- **Run:** created on ask (`running`), updated through stages to `completed`/`failed`. Persisted indefinitely (history + library).
- **Conversation/CostLog/Notes/Saved/Library:** created as the user acts; persist. No automatic expiry (personal tool).
- **DuckDB tables:** derived from files; rebuildable from `data/parquet/`. Dropped when a dataset is deleted.

## Sensitive Data

The dataset itself is the sensitive asset. It is **never sent to the LLM in bulk** — only schema + ≤20 sample rows + small aggregated results (`llm_payload_json` records exactly what left the process). No external transmission beyond those bounded payloads. No auth/PII fields of the agent's own (single local user). Files stay on the local disk under `data/`.
