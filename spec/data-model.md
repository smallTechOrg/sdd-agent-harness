# Data Model

---

## Storage Engine

| Property | Value | Source of truth |
|----------|-------|-----------------|
| Analytics engine | DuckDB | architecture.md Stack > Analytics DB |
| Analytics version pin | `1.1.*` | architecture.md Stack > Analytics DB |
| Analytics DB file path | `./data/app.duckdb` (env `DAA_DUCKDB_PATH`) | architecture.md env var `DAA_DUCKDB_PATH` |
| Metadata engine | SQLite (via aiosqlite) | architecture.md Stack > Metadata spine |
| Metadata version pin | aiosqlite `0.20.*` | architecture.md Stack > DB driver (SQLite) |
| Metadata DB file path | `./data/meta.db` (env `DAA_SQLITE_PATH`) | architecture.md env var `DAA_SQLITE_PATH` |
| Bootstrap | `create_tables_sqlite()` at FastAPI lifespan startup — **no migrations, no Alembic** | architecture.md Startup Sequence step 4 |
| DuckDB driver | `duckdb 1.1.*` | architecture.md Stack > DB driver (DuckDB) |
| Concurrency note | single-writer; DuckDB-locked handling: architecture.md Failure Modes (DuckDB file unavailable / locked) | architecture.md Failure Modes |

| Engine / file | Tables it owns |
|---------------|----------------|
| DuckDB `./data/app.duckdb` | `dataset_<id>` (one persistent table per uploaded file; columnar data) |
| SQLite `./data/meta.db` | `session`, `dataset`, `query_run`, `audit_log` |

**Why this engine (workload tie-in):** Uploaded datasets are scanned analytically with GROUP BY, aggregations, and cross-dataset JOINs (api.md §POST /query → SQL `SELECT … GROUP BY`), so DuckDB's columnar engine fits the read-heavy analytical path; session/dataset metadata and audit bookkeeping are small transactional point writes (one row per session/query/audit event) that fit SQLite's row-store model.

---

## Timestamps & Timezone

- **All `TIMESTAMP` columns are stored in UTC.** `now()` resolves to `CURRENT_TIMESTAMP` in UTC (wall-clock, not monotonic). No exception — every timestamp column in this file is UTC.
- **Duration columns** (`*_ms`) are computed from a **monotonic** clock (`time.monotonic_ns() // 1_000_000`), not wall-clock differences, to avoid DST/NTP skew.

---

## Indexes

| Index name | Table | Columns (in order) | Kind | Driven by (endpoint/node) |
|------------|-------|--------------------|------|---------------------------|
| `ix_dataset_session` | `dataset` | `(session_id)` | index | `GET /datasets` (api.md §GET /datasets), `node_generate_sql` (agent-graph.md) |
| `ix_query_run_session` | `query_run` | `(session_id)` | index | `GET /sessions/{id}/history` (api.md), `node_load_history` (agent-graph.md) |
| `ix_audit_log_session_time` | `audit_log` | `(session_id, created_at)` | index | `GET /sessions/{id}/audit` (api.md) |
| `ix_audit_log_query_run` | `audit_log` | `(query_run_id)` | index | `GET /query/{id}/audit` (api.md) |

[ASSUMPTION: `dataset.name` full-scan acceptable, < 20 rows per session — dataset list is small; no name index needed beyond the UNIQUE constraint.]

---

## Entities

### `session`

A conversation session: created once per browser tab or explicit "New Session" action; groups all queries and datasets belonging to one analytical thread.

| Field | Type | Required | Default | Mutability | Constraint | Notes |
|-------|------|----------|---------|-----------|-----------|-------|
| id | TEXT | yes | NO-DEFAULT (set by POST /sessions) | immutable | PK (uuid4) | server-generated uuid4; ≤ 36 chars |
| created_at | TIMESTAMP | yes | now() | immutable | — | UTC per Timestamps & Timezone |
| title | TEXT | no | null | mutable by: PUT /sessions/{id} | — | user-editable label; ≤ 255 chars; NULL = untitled (auto-labelled from first query) |

### `dataset`

A user-uploaded tabular file registered for querying; the actual columnar data lives in DuckDB table `dataset_<id>`.

| Field | Type | Required | Default | Mutability | Constraint | Notes |
|-------|------|----------|---------|-----------|-----------|-------|
| id | TEXT | yes | NO-DEFAULT (set by POST /datasets) | immutable | PK (uuid4) | server-generated uuid4; ≤ 36 chars |
| session_id | TEXT | yes | NO-DEFAULT | immutable | FK→session.id | must appear in ER diagram |
| name | TEXT | yes | NO-DEFAULT (from upload filename) | immutable | UNIQUE per session_id — [ASSUMPTION: case-sensitive; 'Sales.csv' and 'sales.csv' are distinct] | original filename; ≤ 255 chars |
| file_format | TEXT | yes | NO-DEFAULT (inferred at upload) | immutable | CHECK (file_format IN ('csv','json','excel','parquet')) | one of the four supported formats |
| row_count | INTEGER | yes | NO-DEFAULT (from ingest) | immutable | CHECK (row_count >= 0) | unit: rows; count of rows in the DuckDB table |
| size_bytes | INTEGER | yes | NO-DEFAULT (from upload) | immutable | CHECK (size_bytes >= 0) | unit: bytes; raw file size; max 209715200 (200 MB) per vision.md Hard Constraints |
| column_schema | TEXT | yes | NO-DEFAULT (inferred at upload) | immutable | — | JSON-serialised array; sub-schema below; ≤ 65535 chars [ASSUMPTION: reasonable schema size] |
| duckdb_table | TEXT | yes | NO-DEFAULT (set by POST /datasets) | immutable | — | name of the DuckDB persistent table, always `dataset_<id>`; ≤ 60 chars |
| uploaded_at | TIMESTAMP | yes | now() | immutable | — | UTC per Timestamps & Timezone |

```
column_schema: array<object>   # one entry per column of the uploaded table
  └ object:
      name:     string   required   # source column header; ≤ 255 chars
      dtype:    string   required   # one of: 'TEXT'|'INTEGER'|'DOUBLE'|'BOOLEAN'|'TIMESTAMP'
      nullable: boolean  optional   default true
      sample:   string   optional   # first non-null value as string; ≤ 100 chars; for LLM prompt context
```

### `query_run`

An executed or in-progress NL query tied to a session; append-only (never updated except status); one row per POST /query invocation.

| Field | Type | Required | Default | Mutability | Constraint | Notes |
|-------|------|----------|---------|-----------|-----------|-------|
| id | TEXT | yes | NO-DEFAULT (set by POST /query) | immutable | PK (uuid4) | server-generated uuid4; ≤ 36 chars |
| session_id | TEXT | yes | NO-DEFAULT | immutable | FK→session.id | must appear in ER diagram |
| question | TEXT | yes | NO-DEFAULT | immutable | — | the NL prompt; ≤ 2000 chars (validated at api.md §POST /query) |
| dataset_ids | TEXT | yes | NO-DEFAULT | immutable | — | JSON array of dataset id strings; sub-schema below; ≤ 4096 chars |
| sql | TEXT | no | null | immutable | — | the generated SQL; ≤ 32768 chars; NULL = run failed before SQL was generated |
| row_count | INTEGER | no | null | immutable | CHECK (row_count >= 0) | unit: rows; NULL = run failed or pending |
| status | TEXT | yes | `'pending'` | mutable by: node_finalize, node_handle_error (agent-graph.md) | CHECK (status IN ('pending','done','error')) | the one mutable field; tracks agent run lifecycle |
| error_code | TEXT | no | null | mutable by: node_handle_error (agent-graph.md) | — | the error.code from api.md error matrix; ≤ 50 chars; NULL = no error |
| created_at | TIMESTAMP | yes | now() | immutable | — | UTC per Timestamps & Timezone |

```
dataset_ids: array<string>   # uuid4 ids of datasets referenced in this query
  └ string: uuid4 format; each must exist in dataset.id
```

### `conversation_message`

One turn in a session's conversation history (user question or assistant response); used to build prompt context for follow-up queries; append-only.

| Field | Type | Required | Default | Mutability | Constraint | Notes |
|-------|------|----------|---------|-----------|-----------|-------|
| id | TEXT | yes | NO-DEFAULT (set by node_finalize) | immutable | PK (uuid4) | server-generated uuid4 |
| session_id | TEXT | yes | NO-DEFAULT | immutable | FK→session.id | must appear in ER diagram |
| query_run_id | TEXT | no | null | immutable | FK→query_run.id | NULL = system message not tied to a run |
| role | TEXT | yes | NO-DEFAULT | immutable | CHECK (role IN ('user','assistant','system')) | mirrors standard LLM message roles |
| content | TEXT | yes | NO-DEFAULT | immutable | — | message text; [ASSUMPTION: unbounded — conversation turns are ephemeral and not PII-searchable; max practical length ~8000 chars per turn] |
| created_at | TIMESTAMP | yes | now() | immutable | — | UTC per Timestamps & Timezone |

---

## Relationships (ER)

```
erDiagram
    session         ||--o{ dataset              : has
    session         ||--o{ query_run            : has
    session         ||--o{ conversation_message : has
    session         ||--o{ audit_log            : records
    query_run       ||--o{ audit_log            : generates
    query_run       ||--o{ conversation_message : produces
```

| Relationship | Cardinality | On delete | Rationale (consequence on real data) |
|--------------|-------------|-----------|--------------------------------------|
| session → dataset | 1:N | CASCADE | deleting a session removes its dataset registry rows; DuckDB tables are dropped separately in the delete handler to avoid orphaned columnar data |
| session → query_run | 1:N | CASCADE | deleting a session removes all its query history so no query_run orphans a missing session_id FK |
| session → conversation_message | 1:N | CASCADE | deleting a session removes all conversation turns; history is meaningless without the session |
| session → audit_log | 1:N | CASCADE | audit rows belong to the session; removing the session clears its audit trail |
| query_run → audit_log | 1:N | CASCADE | removing a query_run removes its audit rows; query_run.id is the FK |
| query_run → conversation_message | 1:N | SET NULL | a conversation message's run reference becomes NULL if the run row is deleted, but the message text itself is retained for context continuity |

---

## Audit & Observability Tables

### `audit_log`

A row per SQL execution or LLM call — the inspectable record of every agent action. Cross-ref [harness/patterns/observability.md](../harness/patterns/observability.md) (OTel GenAI attribute names).

| Field | Type | Required | Default | Mutability | Constraint | Notes |
|-------|------|----------|---------|-----------|-----------|-------|
| id | INTEGER | yes | autoincrement | immutable | PK autoincrement | SQLite ROWID; always positive |
| session_id | TEXT | yes | NO-DEFAULT | immutable | FK→session.id | must appear in ER diagram |
| query_run_id | TEXT | no | null | immutable | FK→query_run.id | NULL = a session-level operation not tied to a query |
| run_id | TEXT | yes | NO-DEFAULT | immutable | — | uuid4 correlation id; mirrors agent_state.run_id; ≤ 36 chars |
| created_at | TIMESTAMP | yes | now() | immutable | — | UTC per Timestamps & Timezone |
| action | TEXT | yes | NO-DEFAULT | immutable | CHECK (action IN ('sql','llm','error')) | `sql` for DuckDB execute, `llm` for LLM call, `error` for aborted run |
| payload | TEXT | yes | NO-DEFAULT | immutable | — | the SQL text (action='sql'), the NL prompt (action='llm'), or the error message (action='error'); ≤ 32768 chars; see Sensitive Fields |
| rows_affected | INTEGER | no | null | immutable | CHECK (rows_affected >= 0) | unit: rows; NULL when action is 'llm' or 'error' |
| duration_ms | INTEGER | yes | NO-DEFAULT | immutable | CHECK (duration_ms >= 0) | unit: ms (monotonic); backs SC-6 latency criterion |

**OTel token/cost columns (REQUIRED — LLM provider is in stack):**

| Field | Type | Required | Default | Mutability | Constraint | Notes (OTel attr) |
|-------|------|----------|---------|-----------|-----------|-------------------|
| model | TEXT | for `llm` rows | null | immutable | — | `gen_ai.request.model`; NULL when action is 'sql' or 'error' |
| input_tokens | INTEGER | for `llm` rows | null | immutable | CHECK (input_tokens >= 0) | unit: tokens; `gen_ai.usage.input_tokens`; NULL for non-llm rows |
| output_tokens | INTEGER | for `llm` rows | null | immutable | CHECK (output_tokens >= 0) | unit: tokens; `gen_ai.usage.output_tokens`; NULL for non-llm rows |

**Write sites:**

| Action value | Written by | Cross-ref |
|--------------|-----------|-----------|
| `sql` | agent node `node_execute_sql` | agent-graph.md §node_execute_sql |
| `llm` | agent node `node_generate_sql` | agent-graph.md §node_generate_sql |
| `error` | agent node `node_handle_error` | agent-graph.md §node_handle_error |

### Audit criteria (EARS + acceptance tests)

- **Criterion (Event):** WHEN the agent executes a query, the system SHALL append exactly one `audit_log` row with `action='sql'`, a non-empty `payload` (the SQL text), and `duration_ms >= 0`.
- **Acceptance test:** `pytest tests/test_audit.py::test_sql_logged` — `assert SELECT count(*) FROM audit_log WHERE action='sql' AND session_id=<id>` increments by exactly 1 AND latest row `duration_ms IS NOT NULL AND duration_ms >= 0`.

- **Criterion (Atomicity — State-Driven):** WHILE recording a SQL action, the system SHALL write the `audit_log` row in the SAME transaction as the `query_run` status update, so that a FAILED SQL execution leaves either 0 `audit_log` rows with `action='sql'` for that run OR exactly 1 row paired with `query_run.status='error'`. The audit write and query_run update commit or roll back together.
- **Acceptance test (failure path):** `pytest tests/test_audit.py::test_failed_sql_no_orphan_row` — inject a DuckDB execution error; `assert SELECT count(*) FROM audit_log WHERE action='sql' AND query_run_id=<id>` == 0 (rolled back) OR == 1 paired with `SELECT status FROM query_run WHERE id=<id>` == 'error'.

---

## Lifecycle & Retention

| Entity | Created by | Updated by (derived from Mutability) | Deleted by / retention |
|--------|-----------|--------------------------------------|------------------------|
| session | POST /sessions (api.md) | PUT /sessions/{id} (title field only) | DELETE /sessions/{id} (→ Phase 3); else persists until `./data/meta.db` file deleted |
| dataset | POST /datasets (api.md) | never (append-only) | DELETE /datasets/{id} (→ Phase 3); else persists until `./data/meta.db` deleted; DuckDB table `dataset_<id>` dropped in the same transaction |
| query_run | node_finalize / node_handle_error after POST /query (agent-graph.md) | status and error_code mutable by: node_finalize, node_handle_error | CASCADE with session; no separate delete path |
| conversation_message | node_finalize (agent-graph.md) | never (append-only) | CASCADE with session; query_run_id SET NULL if query_run deleted |
| audit_log | node_generate_sql, node_execute_sql, node_handle_error (agent-graph.md) | never (append-only) | CASCADE with session; no separate retention policy; entire file deleted with `./data/meta.db` |

---

## Sensitive Fields

| Field | Entity / location | Classification | Protection (at rest, in transit, in logs/traces) |
|-------|-------------------|----------------|---------------------------------------------------|
| `DAA_ANTHROPIC_API_KEY` | env var only | secret | never persisted, never logged; stored as `pydantic.SecretStr`; cross-ref architecture.md env vars + harness/rules/secret-hygiene.md |
| `audit_log.payload` | SQLite `./data/meta.db` | PII-unknown (treat as PII per decision rule) | not exported via any list API; redacted in traces when `TRACE_INCLUDE_SENSITIVE_DATA=false`; local file only, never transmitted to external service |
| `conversation_message.content` | SQLite `./data/meta.db` | PII-unknown (treat as PII — user questions may contain personal data) | local file only; not exported via list API; redacted in traces; deletion path: CASCADE with session |
| Uploaded dataset cells | DuckDB `./data/app.duckdb` | PII-unknown (treat as PII — uploaded data may contain personal records) | local file only; encrypted-at-rest: NO (local demo; user controls their machine); never transmitted to Google Gemini beyond the column-schema summary used in prompts; deletion path: DROP TABLE `dataset_<id>` via DELETE /datasets/{id} (→ Phase 3) |

No PII or secrets persisted beyond the above; API keys live only in env vars per architecture.md. Sensitive local files (`./data/`) are excluded from `git add` via `.gitignore`.
