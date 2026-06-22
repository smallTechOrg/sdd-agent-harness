# Architecture

## System Overview

The Data Analyst Agent is a two-tier web application. A browser-based frontend presents a chat-style interface where the user manages datasets and submits natural-language queries. A backend service owns all stateful work: storing uploaded files, maintaining session state, translating questions to SQL via the Gemini API, executing SQL against the uploaded data using an embedded analytical query engine, and writing every operation to an append-only audit log. No data leaves the server except the table schema sent to Gemini.

## Component Map

```
[Browser — Next.js 15 / React 19]
        |  HTTP REST + multipart upload (fetch, port 8001)
        v
[FastAPI Backend  —  uvicorn, port 8001]
    |           |           |           |
    v           v           v           v
[Session     [Dataset    [NL→SQL     [Audit
 Store]       Store]      Service]    Log]
(SQLite)   (filesystem)  (Gemini)   (SQLite)
    |           |
    v           v
[Session     [DuckDB
 JSON blob]   Query Engine]
                |
                v
         [Dataset files on
          local filesystem]

[Gemini API]   (external — schema only, no row data)
```

## Layers

| Layer | Responsibility | Implementation |
|-------|----------------|----------------|
| Web UI | Dataset upload form, chat input, formatted table rendering, session continuity across page loads, stub-mode banner | Next.js 15 App Router + React 19; native `fetch`; Tailwind CSS v4 |
| Backend API | Request routing, input validation (Pydantic), response formatting, error normalisation | FastAPI on uvicorn, port 8001 |
| Session Store | Server-side persistence of session metadata and conversation history; keyed by session ID cookie | SQLite table `sessions` via SQLAlchemy 2.0 + Alembic; session state (datasets + conversation) stored as a JSON blob in `state_json` column |
| Dataset Store | Local filesystem storage of uploaded files at `data/datasets/<session_id>/`; metadata held in the session store JSON blob | Python `pathlib` + `shutil`; DuckDB reads files by path |
| NL→SQL Service | Constructs the Gemini prompt (system instruction + schema + user question), calls the Gemini client, extracts and validates the returned SQL | `services/nl_query.py`; `llm/gemini_client.py` (real) or `llm/stub_client.py` (stub when key absent) |
| Query Engine | Executes validated SQL against uploaded dataset files via DuckDB; caps results at 1 000 rows; enforces 30-second timeout | `services/query_engine.py`; per-request DuckDB connection |
| Audit Log | Append-only record of every SQL execution event | SQLite table `audit_log` in the same `data/app.db`; `services/audit_service.py` |

## Data Flow

1. **Upload trigger:** User selects a CSV or JSON file in the Web UI and submits the upload form.
2. The Backend API receives the file via `POST /api/datasets`, validates size (≤50 MB) and extension (`.csv`/`.json`), writes it to `data/datasets/<session_id>/`, infers column names and types via DuckDB schema introspection, and stores `DatasetMeta` in the session JSON blob. Returns the `DatasetMeta` to the UI.
3. **Query trigger:** User types a natural-language question in the chat input and submits via `POST /api/query`.
4. The Backend API resolves the active session from the `session_id` cookie. The NL→SQL Service retrieves all dataset schemas from the session JSON blob.
5. The NL→SQL Service sends a minimal prompt to the Gemini API: fixed system instruction + schema only (no row data, no conversation history) + user question.
6. Gemini returns a SQL string. The NL→SQL Service extracts the SQL and applies a keyword blocklist (rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`). A second gate in the Query Engine validates that the root AST node is a `SELECT` using `sqlglot`.
7. The Query Engine opens a per-request DuckDB connection, registers the session's dataset files as views, executes the validated SQL with a 30-second timeout, and caps the result at 1 001 rows (returns 1 000 + `truncated: true` if over).
8. The Audit Log appends an `AuditLogRow` to the `audit_log` SQLite table. An audit write failure is logged to stderr but does not prevent the query result from being returned.
9. The Backend API appends user and assistant `ConversationTurn` records to the session JSON blob, persists the updated session, and returns the result set (`columns`, `rows`, `sql`, `truncated`, `total_row_count`) to the Web UI.
10. The Web UI renders the result as a paginated table (25 rows/page) with the SQL visible in a collapsible `<details>` element.

## Session State Architecture

Sessions are stored in SQLite (`data/app.db`), table `sessions`. Each row holds:

```
session_id      TEXT PRIMARY KEY
created_at      TIMESTAMP WITH TIME ZONE
last_active_at  TIMESTAMP WITH TIME ZONE
state_json      TEXT   -- JSON-serialised Session domain model (DatasetMeta list + ConversationTurn list)
```

The `state_json` column holds the full `Session` Pydantic model serialised to JSON. This avoids separate tables for datasets and conversation turns while keeping the data queryable by `session_id`. On read, the service deserialises `state_json` into a `Session` domain object; on write, it re-serialises the whole object. Last-write-wins semantics are acceptable for single-user deployment.

## LLM Abstraction and Stub Mode

The `GeminiProvider` protocol defines a single method:

```python
class GeminiProvider(Protocol):
    def generate_sql(self, system_instruction: str, schema_text: str, question: str) -> str: ...
```

`Settings.resolved_llm_provider` checks whether `GEMINI_API_KEY` is set (non-empty after stripping inline comments). The API factory (`create_app` lifespan) injects either `GeminiClient` (real) or `StubGeminiClient` into the application state. No user flag is required — setting the key is sufficient.

`StubGeminiClient` always returns:
```sql
SELECT * FROM stub_table -- stub-nl-query
```
The `-- stub-nl-query` tag is how the UI detects stub mode (the `/api/sessions/current` response also includes `stub_mode: bool`).

## SQL Validation (Two Gates)

| Gate | Location | Method | Rejects |
|------|----------|--------|---------|
| 1 — Keyword blocklist | `services/nl_query.py` (after Gemini response) | Regex word-boundary scan | Any DML/DDL token |
| 2 — AST check | `services/query_engine.py` (before DuckDB execute) | `sqlglot.parse_one(sql)` root node check | Any non-SELECT root statement |

Passing both gates is required before DuckDB execution.

## Dataset Table Name Normalisation

Dataset file names are normalised to DuckDB view names:

```
original_filename → strip extension → lower() → replace(" ", "_") → replace("-", "_")
```

Example: `"Sales Data Q1-2024.csv"` → `"sales_data_q1_2024"`

SQL table references are matched case-insensitively to this normalised name. An `unknown_table` error is raised (HTTP 422) if the SQL references a name not present in the session.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API | Translate natural-language question to SQL | Return HTTP 502 `llm_unavailable` to user; do not retry automatically |
| Local filesystem (datasets) | Persist uploaded dataset files | Backend startup check; refuse uploads if `data/datasets/` is not writable |
| Local filesystem (SQLite) | Session and audit persistence | HTTP 500; log to stderr |

## Deployment Model

Single-process, single-server deployment. The backend runs as `uvicorn analyst.api:app --port 8001`. The Next.js frontend is served from port 3000 (dev) or as a static export co-located with the backend (production). All state (`data/app.db`, `data/datasets/`) is on the local filesystem. No external database, no cloud storage, no container orchestration required for Phase 1.

The `data/` directory is gitignored. A `.env` file at the repo root provides `ANALYST_DATABASE_URL`, `ANALYST_SECRET_KEY`, and optionally `GEMINI_API_KEY`.

## File Layout (runtime paths)

```
data/
  app.db                              ← SQLite: sessions + audit_log tables
  datasets/
    <session_id>/
      <original_filename>             ← uploaded CSV or JSON file
```

Paths are stored as absolute paths in the `DatasetMeta.file_path` field so they remain valid regardless of working directory changes.
