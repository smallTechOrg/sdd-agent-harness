# Data Model

---

## Storage Technology

Two stores, by design (see `architecture.md`):

- **SQLite** (SQLAlchemy 2.0 + Alembic) — app state and the audit trail: datasets, runs, and (Phase 3) sessions and notes. URL `AGENT_DATABASE_URL` (default `sqlite:///./data/agent.db`).
- **DuckDB** — the query/compute engine over uploaded data. Each dataset's rows live in a **per-dataset DuckDB file** on disk (path referenced by the `Dataset` row). Raw rows live ONLY here and never enter an LLM prompt.

The existing `RunRow` (`runs` table) from the skeleton is **extended** (not replaced) for the audit trail.

## Entities

### Entity: Dataset

An uploaded tabular file ingested into a local DuckDB file.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | Original filename |
| duckdb_path | str | yes | Path to the per-dataset DuckDB file (local only) |
| table_name | str | yes | Table name inside DuckDB (e.g. `data`) |
| schema_json | JSON (text) | yes | `[{name, type}, ...]` — column names + DuckDB types; LLM-visible |
| row_count | int | yes | Number of rows (computed at ingest by DuckDB) |
| profile_json | JSON (text) | no | Per-column stats (nulls, distinct, min/max) — **Phase 2** |
| session_id | str | no | Owning session — **Phase 3** |
| created_at | timestamp | yes | Ingest time |

### Entity: Run (extends existing `runs` table)

One analysis (question → answer). The audit trail.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key (existing) |
| status | str | yes | `pending` / `completed` / `failed` (existing) |
| dataset_id | str | no | Dataset queried (NEW) |
| question | str | no | The plain-English question (NEW; `input_text` retained for compatibility) |
| sql | str | no | The exact generated DuckDB SQL (NEW) |
| result_json | JSON (text) | no | Aggregate result rows (NEW) |
| output_text | str | no | Serialized answer for display (existing) |
| error_message | str | no | Failure reason if `failed` (existing) |
| tokens_json | JSON (text) | no | Prompt/completion tokens + est. cost (NEW; surfaced in UI Phase 3) |
| created_at | timestamp | yes | Existing |
| updated_at | timestamp | yes | Existing |

### Entity: Session — **Phase 3**

A persistent upload-once-ask-many session across days.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| title | str | no | User-facing label |
| turns_json | JSON (text) | no | Conversation turns (Q/A) for follow-up context |
| created_at | timestamp | yes | Created |

### Entity: DataNote — **Phase 3**

A user note about a dataset ("revenue is in cents"), fed into prompts.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | Dataset the note describes |
| text | str | yes | The note |
| created_at | timestamp | yes | Created |

### Relationships

- `Run.dataset_id` → `Dataset.id` (many runs per dataset).
- `Dataset.session_id` → `Session.id` (Phase 3; many datasets per session).
- `DataNote.dataset_id` → `Dataset.id` (Phase 3; many notes per dataset).

## Data Lifecycle

- **Dataset:** created on upload (SQLite row + DuckDB file). Persists until the user deletes it. Phase 1 keeps it for the running session; Phase 3 makes it durable across restarts.
- **Run:** created per question, never deleted (audit trail). Browsable in Phase 3.
- **Session / DataNote:** Phase 3; persist across restarts.

## Sensitive Data

The uploaded data is the user's own and may be sensitive — that is precisely why it stays **local in DuckDB** and **never** enters an LLM prompt as raw rows (privacy invariant, `architecture.md`). The Gemini API key is a secret, stored only in `.env` (`AGENT_GEMINI_API_KEY`), never persisted to the DB or logged.
