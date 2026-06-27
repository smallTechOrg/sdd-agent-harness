# Data Model

---

## Storage Technology

SQLite (`sqlite:///./data/agent.db`) via SQLAlchemy 2.0 + Alembic — this is the production database for a local, single-user personal tool (there is no PostgreSQL). **Raw CSV rows are NOT stored in the database.** Raw files live on the local filesystem under `data/datasets/{dataset_id}.csv`; SQLite holds only metadata, schema, and run history. This split is the storage-level expression of the privacy boundary (see [architecture.md](architecture.md#the-privacy-data-boundary-first-class-architectural-concern)).

## Entities

### Entity: DatasetRow

Metadata for one uploaded CSV. The raw rows are never a field here — only the derived schema.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key; the `dataset_id` returned to the client |
| filename | str | yes | Original upload filename (display only) |
| row_count | int | yes | `len(df)` computed locally at upload |
| schema_json | str (JSON) | yes | Serialized list of `{name, dtype, friendly_dtype}` — column metadata only, no values |
| created_at | datetime (tz) | yes | Upload time |
| updated_at | datetime (tz) | yes | Last touch |

> The raw file path is derived deterministically (`data/datasets/{id}.csv`), so no path field is stored.

### Entity: DataProfile (in-memory, NOT persisted)

The compact derived artifact the agent computes locally and is the ONLY data-bearing object allowed near the LLM prompt. Computed on demand by `load_profile`; never written to the DB and never contains raw rows.

| Field | Type | Description |
|-------|------|-------------|
| row_count | int | Number of rows |
| columns | list of `{name, dtype, friendly_dtype}` | Schema |
| stats | dict per column | Numeric: min/max/mean/median/std/null_count; categorical: distinct_count, top values + counts; capped |
| examples | dict per column | ≤5 truncated example values per column (each value string-capped) |

### Entity: RunRow (extends skeleton)

One question→answer run. Reuses the skeleton's `runs` table, repurposing fields for this domain.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key; the `run_id` |
| dataset_id | str | yes (new column) | FK-by-convention to `DatasetRow.id` |
| input_text | str | yes | The user's question (reuses skeleton column) |
| output_text | str \| null | no | The plain-English answer (reuses skeleton column) |
| status | str | yes | `pending` \| `completed` \| `failed` |
| error_message | str \| null | no | Human-readable error on failure |
| created_at / updated_at | datetime (tz) | yes | Timestamps |

### Relationships

- `RunRow.dataset_id` → `DatasetRow.id` (many runs per dataset). Enforced by convention (single-user local tool); a missing dataset surfaces as a `failed` run with human copy, not a DB constraint error.

## Data Lifecycle

- **Create:** `DatasetRow` + raw file written on upload; `RunRow` written per ask.
- **Update:** `RunRow.status`/`output_text`/`error_message` updated when the run finishes.
- **Delete:** none in Phase 1 (personal tool; the user can delete `data/` manually). Dataset deletion UI is deferred.
- **Time-boxing:** none.

## Sensitive Data

- The **raw CSV** may contain anything the user uploads (potentially PII). It is the protected asset: it stays on local disk and is **never** transmitted to Gemini or persisted in the DB. Only the derived `DataProfile` (aggregates + truncated examples) and the question cross the boundary.
- No auth/secrets stored. The Gemini API key lives in `.env` (`AGENT_GEMINI_API_KEY`), never in the DB.
