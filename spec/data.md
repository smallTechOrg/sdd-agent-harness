# Data Model

> SQLite (app state) via SQLAlchemy 2.0. DuckDB files (the actual data) live on disk under `data/duckdb/` and are NOT modelled here — only their path is stored.

---

## Storage Technology

- **SQLite** (`AGENT_DATABASE_URL=sqlite:///./data/agent.db`) via SQLAlchemy 2.0 + Alembic — app state: datasets and question runs. Reused from the skeleton's `src/db`.
- **DuckDB** — one local file per dataset under `data/duckdb/{dataset_id}.duckdb`, holding the full data. Accessed directly by `src/analysis`, never via SQLAlchemy. The full data never leaves the machine.
- **Filesystem** — original uploads under `data/uploads/{dataset_id}/`.

## Entities

### Entity: Dataset

A profiled CSV the user uploaded and can query.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | Primary key |
| name | Text | yes | Display name (original filename) |
| source_path | Text | yes | Path to the uploaded file under `data/uploads/` |
| duckdb_path | Text | yes | Path to the local DuckDB file under `data/duckdb/` |
| table_name | Text | yes | DuckDB table name the CSV was loaded into |
| schema_json | Text (JSON) | yes | Column names + DuckDB types (the schema sent to the LLM) |
| profile_json | Text (JSON) | yes | Row count, per-column null/distinct counts, numeric min/max — the health summary |
| row_count | Integer | yes | Total rows (for the profile card) |
| status | Text | yes | `"ready"` \| `"failed"` (ingest outcome) |
| error_message | Text | no | Ingest failure reason if `status="failed"` |
| created_at | TIMESTAMP | yes | Upload time |
| updated_at | TIMESTAMP | yes | Last touched |

### Entity: QuestionRun

One natural-language question answered over a dataset — the audit record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | Primary key (the `run_id`) |
| dataset_id | Text (FK → Dataset.id) | yes | The dataset queried |
| question | Text | yes | The user's natural-language question |
| plan | Text | no | The plan the agent produced |
| sql | Text | no | The final executed DuckDB SQL |
| trace_json | Text (JSON) | no | The step trace (tried / failed / worked, with errors + latency) |
| result_json | Text (JSON) | no | The summary table data returned to the UI (bounded) |
| chart_json | Text (JSON) | no | The chosen chart spec `{type, x, y}` |
| answer | Text | no | The plain-English answer with key numbers |
| key_numbers_json | Text (JSON) | no | The called-out figures |
| cost_usd | Float | no | Per-question LLM cost (from token usage) |
| status | Text | yes | `"completed"` \| `"failed"` |
| error_message | Text | no | Failure reason (incl. exhausted SQL retries) |
| created_at | TIMESTAMP | yes | Ask time |
| updated_at | TIMESTAMP | yes | Completion time |

### Relationships

- `Dataset` 1 ──< `QuestionRun` (many runs per dataset; `QuestionRun.dataset_id` → `Dataset.id`).
- Later phases add: `Message` (Phase 3, conversation turns per dataset), `Note` (Phase 5, column/business-rule notes per dataset).

## Data Lifecycle

- **Dataset** created on upload (after successful ingest + profile). Persists across sessions (Phase 2 browses them). No auto-expiry in Phase 1; deletion is out of scope for Phase 1.
- **QuestionRun** created per `ask`, finalized on completion/failure. Immutable audit record; persists for history (Phase 2).
- **Phase 2 reads this history, no new schema.** The Phase-1 tables already hold everything the dataset browser needs: `GET /datasets` reads `Dataset` rows (id, name, row_count, status, created_at + a `COUNT` of related `QuestionRun`s), and `GET /datasets/{id}/runs` reads `QuestionRun` rows and reconstructs each answer from the already-persisted `result_json` / `chart_json` / `answer` / `key_numbers_json` / `trace_json`. `created_at` (descending) drives "newest first" for both the dataset list and the per-dataset run history. **No new table and no Alembic migration is required for Phase 2.**
- **DuckDB / upload files** created on ingest, kept alongside the dataset row. Removed only if the dataset is deleted (later).

## Sensitive Data

- The **raw data** in the CSV / DuckDB file is the sensitive asset. It stays on the local machine and is **never sent to the LLM** — only `schema_json` and bounded aggregates (enforced by the `privacy_guard` node, see [`agent.md`](agent.md)). `result_json` stored on `QuestionRun` is the bounded summary table shown in the UI, not a full data dump.
- No external secrets beyond `AGENT_GEMINI_API_KEY` in `.env` (never logged).
