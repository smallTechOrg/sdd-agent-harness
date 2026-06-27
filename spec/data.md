# Data Model

> DataChat's metadata store. **Raw data rows are never stored in the database** — they live only as files under `./data/uploads/`. The DB holds references (path + schema JSON) plus the chat history.

---

## Storage Technology

- **Metadata:** SQLite via SQLAlchemy 2.0 (existing `Base` in `src/db/models.py`), production DB for this app (`sqlite:///./data/agent.db`). Migrations via Alembic — these new tables require a **new migration** `alembic/versions/0002_datachat.py` (the existing `0001_initial.py` only creates `runs`).
- **Raw files:** stored on the local filesystem at `./data/uploads/<dataset_id>.<ext>` (gitignored). This is the only place raw rows exist. The aggregation engine (`src/data/`) is the only code that reads them.

## Entities

### Entity: Dataset

A single uploaded CSV/Excel file and its inferred schema. Holds a **path reference** and the schema — never the row data.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | Primary key |
| filename | Text | yes | Original upload filename (e.g. `sales_2024.csv`) |
| stored_path | Text | yes | Local path under `./data/uploads/` (raw rows live here, not in DB) |
| file_type | Text | yes | `csv` or `xlsx` |
| schema_json | Text (JSON) | yes | `{"columns": [{"name": ..., "dtype": ...}], "row_count": N}` — LLM-safe, no rows |
| row_count | Integer | yes | Number of data rows (denormalized from schema for convenience) |
| created_at | TIMESTAMP | yes | When uploaded |

### Entity: Conversation

A chat thread scoped to one dataset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | Primary key |
| dataset_id | Text (FK → Dataset.id) | yes | Which dataset this conversation is about |
| created_at | TIMESTAMP | yes | When the conversation started |

### Entity: Message

One turn in a conversation. Assistant messages may carry a chart spec.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | Primary key |
| conversation_id | Text (FK → Conversation.id) | yes | Owning conversation |
| role | Text | yes | `user` or `assistant` |
| content | Text | yes | The message text (question or plain-language answer) |
| chart_json | Text (JSON, nullable) | no | ChartSpec for assistant messages that include a chart (see [api.md](api.md#chart-spec)) |
| created_at | TIMESTAMP | yes | Ordering within the thread |

> The existing `RunRow` (`runs` table) is reused per turn to track agent run status/errors — unchanged. `Message` is the user-facing chat record; `runs` is the internal execution record.

### Relationships

- `Dataset` 1—N `Conversation` (a dataset can have multiple conversations).
- `Conversation` 1—N `Message` (ordered by `created_at`).
- `Message.chart_json` is denormalized JSON (no separate chart table — charts are render-only specs).

## Data Lifecycle

- **Create:** `Dataset` + its file on upload. `Conversation` on the first `/chat` call without a `conversation_id`. `Message` rows per user question and per assistant answer.
- **Update:** none in Phase 1 (records are append-only; the file is immutable once uploaded).
- **Delete:** not exposed in Phase 1 (single local user; manual cleanup of `./data/`). A delete endpoint that removes the row + the file is a possible later addition.
- **No time-boxing/archival** in Phase 1.

## Sensitive Data

- **The uploaded file is the sensitive asset.** Its raw rows are PII-bearing by assumption and **must never enter an LLM prompt** — enforced structurally by the agent graph (only `schema_json` and locally-computed aggregate tables reach Gemini; see [agent.md](agent.md)).
- Files live in a gitignored local directory; nothing about row contents is persisted to the DB beyond aggregate-derived chat answers the user themselves requested.
- `AGENT_GEMINI_API_KEY` is a secret, kept in `.env` (gitignored), accessed only via `src/config/settings.py`.
