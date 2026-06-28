# Data Model

## Storage Technology

SQLite via SQLAlchemy 2.0 (existing `src/db`). **SQLite is the production database** for this
single-local-user app, so tests run against SQLite and that is valid. Raw spreadsheet files
are stored on disk under `uploads/<dataset_id>/<filename>`; the DB stores only metadata,
profile JSON, conversation, and run history — never the bulk raw rows. Migrations via Alembic.

The baseline ships a `runs` table tied to the old `transform_text` slot; Phase 1 **redefines**
`runs` for analysis runs (see below) and adds `datasets`, `conversations`, `messages` via an
Alembic migration.

## Entities

### Entity: dataset  *(Phase 1 — real)*

A persisted, profiled spreadsheet file.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | Display name (original filename) |
| file_path | str | yes | Path under `uploads/` |
| file_type | str | yes | `csv` \| `xlsx` (P1: `csv` only) |
| size_bytes | int | yes | File size |
| row_count | int | yes | Rows in the (primary sheet) frame |
| profile_json | JSON (text) | yes | Schema, dtypes, per-column stats, ≤5-row sample |
| sheet_names | JSON (text) | no | (P4) Excel sheet names |
| created_at | datetime | yes | Upload time |

### Entity: conversation  *(Phase 1 — real)*

A long-lived chat session, scoped to a dataset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | FK → dataset.id (P4: may span multiple) |
| title | str | no | Optional title |
| created_at | datetime | yes | Created |
| updated_at | datetime | yes | Last activity |

### Entity: message  *(Phase 1 — real; powers conversation memory)*

One turn in a conversation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| conversation_id | str | yes | FK → conversation.id |
| role | str | yes | `user` \| `assistant` |
| content | str | yes | The turn text (user question or assistant answer) |
| run_id | str | no | FK → run.id when this assistant turn came from an agent run |
| created_at | datetime | yes | Ordering |

### Entity: run  *(Phase 1 — real; redefines the baseline `runs` table)*

One agent execution answering one question.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | FK → dataset.id |
| conversation_id | str | no | FK → conversation.id |
| question | str | yes | The user's question |
| plan | str | no | Generated plan |
| code | str | no | Generated pandas code (visible in UI) |
| result_preview | str | no | Head-truncated/aggregated result preview (JSON/text) |
| answer | str | no | Plain-English answer |
| chart_spec_json | JSON (text) | no | (P3) chart type + aggregated series |
| status | str | yes | `pending` \| `completed` \| `failed` \| `needs_clarification` |
| error_message | str | no | Set on failure |
| iterations | int | no | Refine-loop passes used |
| prompt_tokens | int | no | (P2 surfaces) accumulated prompt tokens |
| completion_tokens | int | no | (P2 surfaces) accumulated completion tokens |
| cost_usd | float | no | (P2 surfaces) estimated cost |
| created_at | datetime | yes | Start time |
| completed_at | datetime | no | End time (for elapsed/duration) |

> P1 captures `prompt_tokens`/`completion_tokens`/`cost_usd` in the DB if cheaply available,
> but the **cost UI panel is a stub** until Phase 2. The `chart_spec_json` column is written
> in Phase 3.

### Entity: column_note  *(Phase 4 — later)*

User-authored notes / business rules the agent must respect.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| dataset_id | str | yes | FK → dataset.id |
| column_name | str | no | Null = dataset-wide rule |
| note | str | yes | e.g. "`amt` is in cents", "exclude status='void'" |
| created_at | datetime | yes | Created |

### Relationships

- `dataset` 1—N `conversation`, `run`, `column_note`.
- `conversation` 1—N `message`; a `message` may reference a `run`.
- `run` belongs to a `dataset` and optionally a `conversation`.

## Data Lifecycle

- **Create:** dataset on upload; conversation on first question against a dataset; message per
  turn; run per question.
- **Update:** conversation `updated_at` on each turn; run fields filled progressively then on
  finalize.
- **Delete:** datasets (and their files + cascading rows) deletable from the Library (Phase 2).
  No automatic time-boxing — this is the user's personal archive.

## Sensitive Data

The raw spreadsheets are the user's private data — they stay on local disk and in
server-memory only; **never sent to the LLM beyond the ≤5-row sample** (see
[architecture.md → Privacy Data-Flow Boundary](architecture.md)). `profile_json` and
`result_preview` are aggregated/truncated by design. No third-party transmission of rows. No
secrets stored in the DB; the Gemini key lives in `.env` only.
