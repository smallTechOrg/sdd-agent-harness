# Data Model

## Storage Technology

SQLite via SQLAlchemy 2.0 (Mapped types) + Alembic migrations. One file (`datachat.db`) at the repo root; path configurable via `DATACHAT_DATABASE_URL`.

## Tables

### sessions

Represents one uploaded dataset.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| filename | TEXT | Original filename |
| status | TEXT | `uploading` \| `ready` \| `error` |
| row_count | INTEGER | Parsed row count |
| column_names | TEXT | JSON array of column names |
| error_message | TEXT NULL | Set on parse failure |
| created_at | TIMESTAMP | UTC |
| updated_at | TIMESTAMP | UTC, auto-updated |

### messages

One row per user/assistant turn within a session.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| session_id | TEXT FK→sessions.id | Cascade delete |
| role | TEXT | `user` \| `assistant` |
| content | TEXT | Message body |
| reasoning_trace | TEXT NULL | JSON array of action dicts (assistant only) |
| created_at | TIMESTAMP | UTC |

### runs

One row per agent invocation (one per user question).

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| session_id | TEXT FK→sessions.id | |
| status | TEXT | `pending` \| `completed` \| `force_completed` \| `failed` |
| tokens_input | INTEGER | Accumulated |
| tokens_output | INTEGER | Accumulated |
| error_message | TEXT NULL | |
| created_at | TIMESTAMP | UTC |
| updated_at | TIMESTAMP | UTC |

## In-Memory Store

Parsed DataFrames are held in a module-level dict `_dataframe_store: dict[str, pd.DataFrame]` in `graph/nodes.py`, keyed by `session_id`. This is intentional for v0.1 (single-process, no persistence needed for DataFrames). Cleared in all terminal nodes.

## Domain Models (Pydantic)

| Class | Purpose |
|-------|---------|
| `Session` | API-facing session representation |
| `Message` | API-facing message representation |
| `Run` | API-facing run representation |
