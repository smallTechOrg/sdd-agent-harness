# Data Model

## Storage Technology

Two stores, each for what it's good at:

- **SQLite** (binding user override — demo/single-machine; async via `aiosqlite`) — application
  metadata: datasets, uploaded files (+ inferred schema), conversations, messages, and agent runs.
  Durable, relational, queried by the API. The same async SQLAlchemy 2.0 code moves to PostgreSQL by
  changing only the driver/URL if the project outgrows a single machine.
- **DuckDB** (in-process analytical engine) — the actual CSV-derived data. On upload, each file's rows
  are materialized as a **DuckDB table** (one table per file, named from the dataset/file id). The
  ReAct agent's `run_sql` MCP tool executes read-only `SELECT`s against these tables. DuckDB tables are
  **not** modeled in SQLite beyond the `file` record that describes their schema.

Timestamps are **naive UTC** (`datetime.utcnow()`, no tzinfo) — store UTC, format at the edge.

## Baseline agentic entities (start here, then add domain entities)

| Entity | Holds | Layer | When |
|--------|-------|-------|------|
| `runs` | one agent invocation (one question→answer cycle): status, usage (tokens/cost), error, timestamps | 6/9 | **baseline (Phase 1)** |
| `messages` | conversation turns per conversation (the short-term memory record) | 3 (short-term) | **baseline (Phase 1)** |
| `eval_results` | eval case scores (NL-question → expected result) | 9 | with the eval skeleton (Phase 1) |
| `memory_records` | long-term memory | 3 (long-term) | ❌ not used (deferred — see [`02-architecture.md`](02-architecture.md)) |
| `embeddings` / vector table | retrieval | 5 | ❌ not used (deferred) |

## Entities

### Entity: `dataset`

A named collection of one or more uploaded CSV files that a user asks questions about.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| name | string | yes | User-given name, e.g. `"Q1 Sales"` |
| created_at | datetime (naive UTC) | yes | When the dataset was created |

### Entity: `file`

One uploaded CSV belonging to a dataset, with its inferred schema. Each maps to one DuckDB table.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| dataset_id | uuid (FK → dataset) | yes | Owning dataset |
| filename | string | yes | Original filename, e.g. `"sales_2024.csv"` |
| duckdb_table | string | yes | Name of the materialized DuckDB table, e.g. `"ds_<id>_sales_2024"` |
| schema_json | json | yes | Inferred columns + types, e.g. `[{"name":"region","type":"VARCHAR"},{"name":"sales","type":"DOUBLE"}]` |
| sample_rows_json | json | yes | ≤20 sample rows captured for LLM grounding |
| row_count | int | yes | Number of rows loaded |
| created_at | datetime (naive UTC) | yes | When uploaded |

### Entity: `conversation`

A multi-turn chat session bound to exactly one dataset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| dataset_id | uuid (FK → dataset) | yes | The dataset this conversation queries |
| title | string | no | Optional label (e.g. first question) |
| created_at | datetime (naive UTC) | yes | When started |

### Entity: `message`

One turn in a conversation — a user question or an assistant answer. The short-term memory record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| conversation_id | uuid (FK → conversation) | yes | Owning conversation |
| run_id | uuid (FK → run) | no | The run that produced this message (assistant turns) |
| role | enum (`user` / `assistant`) | yes | Who produced the turn |
| content | text | yes | The question text, or the assistant's plain-English answer |
| result_table_json | json | no | Result rows + headers for an assistant answer (null for user turns) |
| trace_json | json | no | The `action_history` (description/result per step) for the assistant turn |
| created_at | datetime (naive UTC) | yes | When created |

### Entity: `run`

One ReAct agent invocation answering a single question — the orchestration + observability record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| conversation_id | uuid (FK → conversation) | yes | The conversation this run belongs to |
| status | enum (`running` / `completed` / `failed`) | yes | Lifecycle status |
| iteration_count | int | yes | Loop iterations used |
| early_exit_reason | string | no | Set when `force_finalize` triggered (e.g. `"max_iterations"`) |
| tokens_input | int | yes | Accumulated input tokens |
| tokens_output | int | yes | Accumulated output tokens |
| estimated_cost_usd | float | no | Estimated cost |
| error_message | text | no | Set on fatal failure |
| started_at | datetime (naive UTC) | yes | When the run began |
| completed_at | datetime (naive UTC) | no | When the run ended |

### Entity: `eval_result`

A score for one eval case (NL question against a fixture dataset vs. a reference result).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | yes | Primary key |
| case_name | string | yes | The eval case identifier |
| passed | bool | yes | Whether the assertion held |
| detail | text | no | What was compared / why it failed |
| created_at | datetime (naive UTC) | yes | When the eval ran |

### Relationships

- `dataset` 1—N `file` (a dataset holds one or more CSV files).
- `dataset` 1—N `conversation` (many conversations can query one dataset).
- `conversation` 1—N `message` (turns in order).
- `conversation` 1—N `run` (one run per assistant turn).
- `run` 1—1 `message` (an assistant message links back to the run that produced it).
- Each `file` maps to exactly one DuckDB table (referenced by `duckdb_table`).

## Data Lifecycle

- **Created** — `dataset` on create; `file` + DuckDB table on upload; `conversation` on first turn;
  `message` + `run` per question.
- **Updated** — `run` status/usage transition during the loop; `message.result_table_json`/`trace_json`
  written when the run finalizes.
- **Deleted** — deleting a dataset removes its files, conversations, messages, runs, **and** drops its
  DuckDB tables (releasing the session-scoped engine resource per
  [`react-agent.md`](../engineering/patterns/react-agent.md) § Resource lifecycle).
- **Volatility** — each dataset's DuckDB tables live in a **file-backed** DuckDB (`.duckdb_store/<dataset_id>.duckdb`),
  so they **persist across process restarts**. If that file is missing (e.g. deleted), the API reports
  the dataset as "not loaded" with an actionable re-upload message rather than answering wrongly. SQLite
  metadata is durable.

## Sensitive Data

- Uploaded CSVs may contain user/business data; it stays in SQLite/DuckDB on the deployment and is
  **never** sent wholesale to the LLM — only schema + a ≤20-row sample. No PII fields are added by the
  system itself.
- `GEMINI_API_KEY`/`GOOGLE_API_KEY` is a secret — env-only, never stored in the DB, never logged
  ([`../engineering/secret-hygiene.md`](../engineering/secret-hygiene.md)).
