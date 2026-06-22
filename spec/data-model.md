# Data Model

## Storage

All persistent state is stored on the local filesystem. There is no external database process. Two storage concerns exist: (1) session records (structured JSON, one file per session) and (2) uploaded dataset files (the raw CSV/JSON files as uploaded). The audit log is a separate append-only structured log file.

> **Assumed:** Session records are stored as JSON files in a `data/sessions/` directory. Dataset files are stored in a `data/datasets/<session_id>/` subdirectory. The audit log is a single append-only NDJSON file at `data/audit.log`. The tech-architect may adjust paths.

## Entities

### Entity: Session

Represents an active user session. One session per browser tab (keyed by cookie). Holds all context needed to resume analysis.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| session_id | UUID string | Yes | Primary key; value of the session cookie |
| created_at | ISO 8601 datetime | Yes | When the session was first created |
| last_active_at | ISO 8601 datetime | Yes | Updated on every API request carrying this session ID |
| datasets | Array of DatasetMeta | Yes | Ordered list of datasets registered in this session (may be empty) |
| conversation | Array of ConversationTurn | Yes | Ordered history of user questions and assistant responses (may be empty) |

### Entity: DatasetMeta

Metadata about one uploaded file. Embedded inside a Session record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| dataset_id | UUID string | Yes | Unique identifier for this dataset within the session |
| name | String | Yes | Logical table name (file name without extension, normalised to lowercase, spaces replaced with underscores) |
| original_filename | String | Yes | The file name as uploaded by the user |
| file_path | String (filesystem path) | Yes | Absolute path to the stored file |
| format | Enum: `csv` or `json` | Yes | File format inferred from extension |
| columns | Array of ColumnDef | Yes | Inferred schema |
| row_count | Integer | Yes | Total number of data rows in the file |
| size_bytes | Integer | Yes | Size of the stored file in bytes |
| uploaded_at | ISO 8601 datetime | Yes | When the file was stored |

### Entity: ColumnDef

A single column in a dataset's inferred schema. Embedded inside DatasetMeta.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | String | Yes | Column name as it appears in the file header |
| type | Enum: `text`, `integer`, `float`, `boolean`, `date`, `datetime` | Yes | Inferred data type |

### Entity: ConversationTurn

A single exchange in the chat history. Embedded inside a Session record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| turn_id | UUID string | Yes | Unique identifier for this turn |
| role | Enum: `user` or `assistant` | Yes | Who produced this message |
| content | String | Yes | For `role: "user"`: the user's question text. For `role: "assistant"` turns written by the Query Execution capability: a fixed template string `"Returned {N} row(s)."` (N = row count; 0 on error). For `role: "assistant"` turns written by nl-query on failure (`sql_rejected` or `llm_unavailable`): a human-readable error message string (e.g. `"Query could not be generated."` or `"The query service is temporarily unavailable."`). Not LLM-generated prose in either case. |
| sql | String or null | No | The SQL statement generated for this turn (present on `assistant` turns that executed a query) |
| result_summary | String or null | No | Brief summary line (e.g. `"Returned 42 row(s)."`). Persisted as part of the ConversationTurn entity in the session record on disk (not only returned in the API response); `content` is the canonical display value. `result_summary` is a denormalised convenience field populated by the Query Execution capability. |
| timestamp | ISO 8601 datetime | Yes | When this turn was created |

### Entity: AuditLogEntry

One record written to the audit log per SQL execution attempt. Stored as NDJSON (one JSON object per line) in the audit log file.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| timestamp | ISO 8601 datetime | Yes | When the execution was attempted |
| session_id | UUID string | Yes | Session that initiated the query |
| source_question | String | Yes | The original natural-language question |
| sql | String | Yes | The SQL statement that was executed (or attempted) |
| row_count | Integer or null | No | Number of rows returned; null on error |
| status | Enum: `success` or `error` | Yes | Outcome of the execution |
| error_message | String or null | No | Error detail if status is `error` |

## Relationships

- One **Session** contains zero or more **DatasetMeta** records (embedded array).
- One **Session** contains zero or more **ConversationTurn** records (embedded array, ordered by timestamp).
- One **DatasetMeta** contains one or more **ColumnDef** records (embedded array).
- **AuditLogEntry** references a Session by `session_id` but is stored independently in the audit log file; there is no enforced foreign-key constraint.
- Each dataset file on the filesystem is referenced by exactly one **DatasetMeta** record's `file_path`.

## Data Lifecycle

| Event | Effect |
|-------|--------|
| First request with no cookie | New Session record created; saved to filesystem |
| File upload | DatasetMeta created; file written to filesystem; Session record updated |
| NL query submitted | ConversationTurn (role: user) appended to Session |
| SQL executed | AuditLogEntry appended to audit log; ConversationTurn (role: assistant) appended to Session |
| Session expires (24 h inactivity) | Session record and dataset files become eligible for deletion; not automatically deleted in Phase 1 |
| Unknown session ID presented | New Session created; old session (if any) is not modified |

## Sensitive Data

- `GEMINI_API_KEY` is an environment variable; it is never written to any file, log, or response payload.
- Uploaded dataset files may contain user business data and should be treated as confidential; they are stored on the local filesystem accessible only to the server process.
- The audit log contains the user's natural-language questions and generated SQL; it should be protected with filesystem-level read permissions appropriate for the deployment environment.
- Session IDs are random UUIDs and should not be logged in any HTTP access log in plaintext.
