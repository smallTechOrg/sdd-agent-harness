# Data Model

## Storage Technology

SQLite via SQLAlchemy 2.0 async with the `aiosqlite` driver. Database file: `data_analysis.db` in the working directory (configurable via `AGENT_DATABASE_URL`). Alembic manages schema migrations. No PostgreSQL; SQLite is the only storage backend.

Raw uploaded files are stored on the local filesystem at `uploads/<file_id>.<ext>` (not in the database).

---

## Entities

### Entity: `uploaded_files`

Represents a file that has been uploaded by the user and profiled. One row per upload.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `VARCHAR(36)` | yes | UUID4 primary key, assigned at upload |
| `original_filename` | `VARCHAR(255)` | yes | Original filename as provided by the browser |
| `file_ext` | `VARCHAR(10)` | yes | Lowercase extension: `csv`, `xlsx` |
| `file_path` | `VARCHAR(512)` | yes | Filesystem path relative to repo root, e.g. `uploads/<id>.csv` |
| `file_size_bytes` | `INTEGER` | yes | File size in bytes at upload time |
| `row_count` | `INTEGER` | yes | Total number of data rows (excluding header) |
| `column_count` | `INTEGER` | yes | Number of columns |
| `profile_json` | `TEXT` | yes | JSON blob: `{columns: [{name, dtype, null_count, sample_values: [3]}], row_count, column_count, file_size_bytes, profiled_at}` |
| `session_id` | `VARCHAR(36)` | no | Foreign key to `sessions.id`; NULL in Phase 1 |
| `created_at` | `DATETIME` | yes | UTC timestamp of upload |

### Entity: `query_runs`

Represents a single NL query submitted by the user. One row per question-answer cycle.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `VARCHAR(36)` | yes | UUID4 primary key |
| `session_id` | `VARCHAR(36)` | no | Foreign key to `sessions.id`; NULL in Phase 1 |
| `file_ids` | `TEXT` | yes | JSON array of `uploaded_files.id` values used in this query |
| `question` | `TEXT` | yes | The user's original natural-language question |
| `answer_text` | `TEXT` | no | Plain-text answer from `synthesize_answer`; NULL if failed |
| `plotly_chart_json` | `TEXT` | no | JSON serialisation of the Plotly figure spec; NULL if no chart or failed |
| `code_steps_json` | `TEXT` | no | JSON array of `ExecutionStep` dicts (iteration, code, stdout, stderr, success, elapsed_s) |
| `iterations_used` | `INTEGER` | no | How many code-execute loop iterations were performed |
| `input_tokens` | `INTEGER` | no | Total input tokens consumed across all LLM calls in this run |
| `output_tokens` | `INTEGER` | no | Total output tokens consumed across all LLM calls in this run |
| `cost_usd` | `FLOAT` | no | Estimated cost in USD |
| `status` | `VARCHAR(20)` | yes | `running`, `completed`, `failed`, `interrupted` |
| `error_message` | `TEXT` | no | Error detail if `status='failed'` |
| `started_at` | `DATETIME` | yes | UTC timestamp when the run started |
| `completed_at` | `DATETIME` | no | UTC timestamp when the run finished (NULL if interrupted) |

### Entity: `sessions` (Phase 2)

Represents a named conversation session grouping multiple query runs and uploaded files.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `VARCHAR(36)` | yes | UUID4 primary key |
| `name` | `VARCHAR(255)` | yes | Human-readable session name; defaults to `"Session <created_at date>"` |
| `created_at` | `DATETIME` | yes | UTC timestamp of session creation |
| `last_active_at` | `DATETIME` | yes | UTC timestamp of last query in this session; updated on each query |

### Entity: `audit_log` (Phase 2)

Immutable append-only record of every query run with full detail for debugging and cost tracking.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `VARCHAR(36)` | yes | UUID4 primary key |
| `query_run_id` | `VARCHAR(36)` | yes | Foreign key to `query_runs.id` |
| `session_id` | `VARCHAR(36)` | no | Denormalised copy from `query_runs.session_id` for fast daily-cost queries |
| `question` | `TEXT` | yes | Copy of `query_runs.question` |
| `answer_text` | `TEXT` | no | Copy of `query_runs.answer_text` |
| `code_steps_json` | `TEXT` | no | Copy of `query_runs.code_steps_json` |
| `input_tokens` | `INTEGER` | no | Copy |
| `output_tokens` | `INTEGER` | no | Copy |
| `cost_usd` | `FLOAT` | no | Copy |
| `elapsed_s` | `FLOAT` | no | Total wall-clock time for the run in seconds |
| `status` | `VARCHAR(20)` | yes | Final status |
| `recorded_at` | `DATETIME` | yes | UTC timestamp when this audit row was written (end of run) |

---

## Relationships

```
sessions 1──* uploaded_files   (session_id FK; NULL in Phase 1)
sessions 1──* query_runs       (session_id FK; NULL in Phase 1)
query_runs 1──1 audit_log      (query_run_id FK; Phase 2+)
```

`query_runs.file_ids` stores a JSON array of `uploaded_files.id` values rather than a join table, because multi-file associations are read-only and query patterns are simple (no need to query "which runs used file X" in Phase 1–3).

---

## Data Lifecycle

- **`uploaded_files`:** Created at upload. Never updated (profile is computed once). Not deleted automatically — files persist until the user manually deletes them (no delete endpoint in Phase 1–3).
- **`query_runs`:** Created at the start of each query (`status='running'`). Updated to `completed` or `failed` at the end of the SSE stream. Rows with `status='running'` older than 5 minutes are set to `interrupted` on server startup.
- **`sessions`:** Created on first query in Phase 2. `last_active_at` is updated on each query. Not deleted.
- **`audit_log`:** Written once at the end of each run (Phase 2+). Immutable — never updated or deleted. Used for cost aggregation queries (`SUM(cost_usd) WHERE DATE(recorded_at) = today`).

---

## Sensitive Data

- **User data files** (`uploads/`): may contain PII depending on the user's CSV content. They are stored locally on the user's machine only (no cloud upload). The application does not log file contents.
- **`query_runs.question`**: may contain sensitive terms. Stored in SQLite (local only); not transmitted anywhere except to the Gemini API (which the user controls via their own API key).
- **API keys**: `AGENT_GEMINI_API_KEY` is read from `.env` (gitignored). Never logged, never stored in the database.
- No encryption at rest is applied — this is a local single-user tool. The operating system's filesystem permissions protect the data.
