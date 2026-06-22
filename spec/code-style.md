# Code Style

> The tech-architect has filled in all language-specific sections. Universal rules and framework gotchas below apply to all phases.

---

## Universal Rules

These apply regardless of language or framework:

1. **Types at boundaries** — every function that crosses a module boundary must use typed inputs and outputs (Pydantic models, TypeScript interfaces) — never raw `dict` or `any`
2. **One responsibility per file** — a file does one thing; if it does two things, split it
3. **No comments explaining WHAT** — code should be self-documenting via names; only comment WHY something non-obvious is done
4. **No dead code** — remove unused imports, functions, and variables immediately; do not comment them out
5. **Fail loudly at startup** — validate all required config/env vars at startup; do not fail silently at runtime
6. **No hardcoding** — values that could change (URLs, limits, credentials) go in config or environment variables

---

## Python (Backend)

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Modules / packages | `snake_case` | `session_store.py`, `query_engine.py` |
| Classes | `PascalCase` | `SessionRow`, `DatasetMeta` |
| Functions / methods | `snake_case` | `infer_schema`, `validate_sql` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RESULT_ROWS`, `STUB_SELECT_SQL` |
| Private functions | `_snake_case` (single leading underscore) | `_parse_csv_schema` |
| Type aliases | `PascalCase` | `ColumnList = list[ColumnDef]` |
| Environment prefix | `ANALYST_` | `ANALYST_DATABASE_URL` |

### File Organisation

Files are grouped **by layer**, not by feature. The layers are:

```
api/          ← HTTP routing only; no business logic
config/       ← settings singleton
db/           ← SQLAlchemy models + session factory
domain/       ← Pydantic data shapes (pure; no I/O)
services/     ← all business logic and I/O
llm/          ← Gemini client abstraction
prompts/      ← .md prompt templates loaded at runtime
```

Rules:
- `api/` handlers validate input and delegate immediately to a `services/` function. No SQL, no file I/O, no Gemini call in an `api/` file.
- `domain/` files contain only Pydantic models and enums. No imports from `services/`, `db/`, or `llm/`.
- `services/` functions are the only layer that may call `db/`, `llm/`, and the filesystem. They return domain models, never SQLAlchemy rows.
- `db/models.py` contains SQLAlchemy `Mapped` column definitions only. No business logic.

### SQLAlchemy Models

Use SQLAlchemy 2.0 `Mapped` types exclusively. No `Column(...)` old-style.

```python
class SessionRow(Base):
    __tablename__ = "sessions"
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Session state (DatasetMeta list + ConversationTurn list) stored as JSON blob
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
```

### Pydantic Models

- All domain models inherit from `pydantic.BaseModel`.
- Use `pydantic.Field(...)` with `description=` for any field that appears in an API response.
- `model_config = ConfigDict(frozen=True)` for value objects that must not be mutated (e.g. `ColumnDef`, `AuditLogEntry`).

### Error Handling Pattern

Three layers, each handling at the right level:

1. **Services** raise typed domain exceptions: `class AnalystError(Exception): code: str; message: str`
2. **API handlers** catch `AnalystError` and call `api_error(code, message, status_code)` to produce the standard error shape `{"error": code, "message": message}`.
3. **Unexpected exceptions** are caught by a FastAPI exception handler that logs at ERROR level and returns HTTP 500 with a generic message. Stack traces never reach the client.

```python
# domain exception (services/exceptions.py)
class AnalystError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code

# api handler pattern
@router.post("/api/query")
async def post_query(body: QueryRequest, session: Session = Depends(get_session)):
    try:
        result = run_query(body.question, session)
        return ok(result)
    except AnalystError as e:
        raise api_error(e.code, e.message, e.status_code)
```

### Logging Pattern

Use `structlog` with JSON output. Every log entry must include:

| Field | Value |
|-------|-------|
| `timestamp` | ISO 8601 UTC (added by structlog processor) |
| `level` | DEBUG / INFO / WARNING / ERROR |
| `event` | Short verb-noun string: `"upload.schema_inferred"`, `"query.duckdb_timeout"` |
| `session_id` | Always include when available — use `structlog.contextvars.bind_contextvars` at request start |

Never log:
- `GEMINI_API_KEY` or any secret
- Raw file contents or row data
- Session IDs in HTTP access logs (only in structlog application logs)

```python
import structlog
log = structlog.get_logger()

log.info("upload.file_stored", session_id=sid, dataset_id=did, size_bytes=size)
log.error("query.duckdb_error", session_id=sid, error=str(exc))
```

### LLM Provider Selection

The `Settings` model exposes a `resolved_llm_provider` property:

```python
@property
def resolved_llm_provider(self) -> str:
    key = (self.gemini_api_key or "").strip().split("#")[0].strip()
    return "gemini" if key else "stub"
```

This strips inline `#` comments from `.env` values before checking (pydantic-settings does NOT do this). The app creates `GeminiClient` when `resolved_llm_provider == "gemini"` and `StubGeminiClient` otherwise. No extra user flag.

### DuckDB Query Execution

- Register dataset files with `duckdb.read_csv_auto(path)` / `duckdb.read_json_auto(path)` — do not copy data into DuckDB tables.
- Set a timeout via `connection.execute("SET query_timeout_ms = ?", [timeout_ms])` before each query.
- Cap result rows: `LIMIT 1001` appended if not already present; if result has 1001 rows, return 1000 + `truncated: true`.
- Table name normalisation: dataset names are stored as `lower(filename_without_extension).replace(" ", "_").replace("-", "_")`. DuckDB view/table references in SQL are matched case-insensitively.

### SQL Validation

Two independent gates:

1. **nl-query** (before Gemini call is used): keyword blocklist check on the returned SQL. Reject if any of `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE` appear as SQL tokens (case-insensitive word-boundary match, not substring).
2. **query-engine** (before DuckDB execution): `sqlglot.parse_one(sql).find(sqlglot.exp.Select)` — reject if the root statement is not a `SELECT`.

Using two separate gates matches the spec requirement (query-engine is a second enforcement gate after nl-query).

### Testing Conventions

- Unit tests: `tests/unit/` — one file per module under test, named `test_<module>.py`.
- Integration tests: `tests/integration/test_pipeline.py` — TestClient golden-path smoke test.
- Test function names are full sentences: `test_upload_rejects_file_exceeding_50mb`, `test_query_returns_truncated_flag_when_over_1000_rows`.
- Fixtures in `tests/conftest.py`:
  - `_reset_settings_singleton` — autouse, resets `analyst.config.settings._settings = None` before each test.
  - `db_session` — creates a fresh SQLite in-memory DB for each test; patches `analyst.db.session._engine` and `_SessionLocal`.
  - `test_client` — returns a `TestClient(create_app())` with the test DB session injected.
- No `monkeypatch.setenv("GEMINI_API_KEY", ...)` in any test that is meant to pass offline — absence of the key triggers the stub automatically.

---

## TypeScript / React (Frontend)

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files (components) | `PascalCase.tsx` | `DatasetSidebar.tsx`, `ResultTable.tsx` |
| Files (utilities/hooks) | `camelCase.ts` | `useSession.ts`, `apiClient.ts` |
| React components | `PascalCase` function | `export function ChatPanel(...)` |
| Custom hooks | `use` prefix | `useSessionState`, `usePaginatedTable` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_PAGE_SIZE`, `API_BASE` |
| Types / interfaces | `PascalCase` | `DatasetMeta`, `ConversationTurn` |
| Event handlers | `handle` prefix | `handleSend`, `handleUpload` |

### File Organisation

```
frontend/src/app/
  layout.tsx           ← root layout; renders StubBanner conditionally
  page.tsx             ← two-panel layout (DatasetSidebar + ChatPanel)
  components/
    DatasetSidebar.tsx ← upload button, dataset list, empty state
    ChatPanel.tsx      ← conversation history, empty state
    ChatInput.tsx      ← text field + Send button; disabled when no datasets
    ResultTable.tsx    ← paginated table; 25 rows/page; numeric right-align
    SqlCollapsible.tsx ← collapsible <details> showing raw SQL
    StubBanner.tsx     ← amber banner; rendered when API returns stub=true
  lib/
    apiClient.ts       ← typed fetch wrappers for all API endpoints
    types.ts           ← TypeScript mirrors of all Pydantic domain models
```

### TypeScript Types

Mirror the Python domain models exactly in `lib/types.ts`. No `any`. Every API response has an interface.

```typescript
// lib/types.ts
export interface ColumnDef { name: string; type: string }
export interface DatasetMeta {
  dataset_id: string; name: string; original_filename: string;
  format: "csv" | "json"; columns: ColumnDef[];
  row_count: number; size_bytes: number; uploaded_at: string;
}
export interface ConversationTurn {
  turn_id: string; role: "user" | "assistant";
  content: string; sql: string | null;
  result_summary: string | null; timestamp: string;
}
export interface QueryResponse {
  turn_id: string; sql: string;
  columns: string[]; rows: unknown[][];
  row_count: number; truncated: boolean; total_row_count: number;
}
export interface ApiError { error: string; message: string }
```

### Error Handling Pattern

Every `fetch` call is wrapped in `apiClient.ts` with a typed error path:

```typescript
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init })
  if (!res.ok) {
    const err: ApiError = await res.json()
    throw new ApiClientError(err.error, err.message, res.status)
  }
  return res.json() as Promise<T>
}
```

Components catch `ApiClientError` and render the error into the chat panel or sidebar — never `console.error` alone, never a raw stack trace in the DOM.

### Stub Banner

The `GET /api/sessions/current` response includes a top-level `stub_mode: boolean` field when the backend is running without a Gemini key. The frontend reads this and renders `<StubBanner>` at the root layout level. The banner:

- Is full-width, amber background.
- Text: "Gemini API key not configured. Set the GEMINI_API_KEY environment variable and restart the server to enable natural-language queries."
- Disappears when `stub_mode` is `false` — no user action required.

### Table Pagination

`ResultTable` manages pagination state with `useState<number>` (current page). Constants:

```typescript
const ROWS_PER_PAGE = 25
```

Numeric columns (detected by checking if all non-null values in the column parse as `Number(v)`) are `text-align: right`. Text columns are `text-align: left`.

### Interaction Rules

- Chat input `<textarea>` is `disabled` when `datasets.length === 0` or when a query is in flight.
- While a query is in flight: the Send button shows a spinner; the input is disabled; no second submission is possible.
- After upload: sidebar updates immediately (no page reload) by re-fetching `GET /api/sessions/current` or optimistically appending the returned `DatasetMeta`.

---

## Error Handling — API Routes

For the REST API (not a template-render app), the pattern from `code-style.md` pipeline-error section is adapted:

```python
# CORRECT — return structured JSON error; do NOT raise HTTPException from business logic
@router.post("/api/query")
async def post_query(body: QueryRequest, db: Session = Depends(get_session)):
    try:
        result = await run_nl_query(body.question, db)
        return ok(result)
    except AnalystError as e:
        raise api_error(e.code, e.message, e.status_code)
    except Exception:
        log.exception("query.unexpected_error")
        raise api_error("internal_error", "An unexpected error occurred.", 500)
```

---

## Framework Gotchas

### Starlette SessionMiddleware

`SessionMiddleware` requires a `secret_key` — must be set via `ANALYST_SECRET_KEY` env var. A missing key causes Starlette to raise at startup (fail-fast is correct behaviour).

### DuckDB and Thread Safety

DuckDB connections are not thread-safe. Create one connection per request (or per service call), not a shared global connection. Use `duckdb.connect()` as a context manager.

### pydantic-settings — `extra="ignore"` required

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANALYST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # .env may contain GEMINI_API_KEY and other unprefixed vars
    )
```

`GEMINI_API_KEY` has no `ANALYST_` prefix — it must NOT be declared as a field on `Settings`. Read it directly with `os.environ.get("GEMINI_API_KEY", "")` inside `resolved_llm_provider`. This keeps it out of the settings model entirely and prevents accidental logging.

### SQLite + Alembic async

Use `aiosqlite` as the async driver (`sqlite+aiosqlite:///...`). The `alembic/env.py` must use a **synchronous** engine for the `run_migrations_online` path (Alembic does not support async natively without `run_sync`). Use `sqlalchemy.create_engine` (sync) in `env.py`; use `create_async_engine` only in the application's `db/session.py`.

### Inline `.env` comment stripping

```python
# In Settings or a helper — ALWAYS strip before comparison
raw = os.environ.get("GEMINI_API_KEY", "")
key = raw.strip().split("#")[0].strip()
is_stub = not key
```

---

## Test Environment Rules

These apply to all phases. No exceptions.

1. **Same DB driver as production** — the production DB is SQLite via `aiosqlite`. Tests use SQLite via `aiosqlite` — not a substitute.
2. **Automated setup** — `conftest.py` creates all tables before tests and tears them down automatically. No manual steps.
3. **Isolated test DB** — `tmp_path` fixture provides a per-test SQLite file; no shared state between tests.
4. **DB URL via env** — `ANALYST_DATABASE_URL` in `.env.example` documents the placeholder; tests override via monkeypatch.
5. **`alembic upgrade head` in README** — explicit step before running app or tests. Never rely on SQLAlchemy `create_all` alone in the documented setup path.

---

## What NOT to Do

| Anti-pattern | Reason |
|--------------|--------|
| Row data in Gemini prompt | Spec constraint + PII risk |
| DML/DDL execution in DuckDB | Security; reject at both nl-query and query-engine layers |
| Global DuckDB connection | Not thread-safe; create per request |
| `import *` | Hides what is available; breaks static analysis |
| Mutable default arguments | Classic Python footgun: `def f(x=[])` |
| `os.system` / `subprocess` for SQL | Always use DuckDB's Python API |
| `json.dumps` in SQLAlchemy column setters without validation | Run through Pydantic model before storing |
| `any` type in TypeScript | Defeats type checking at API boundary |
| Frontend storing session state in `localStorage` | Session state is server-side by design; cookie only |
| Sending `conversation` history to Gemini | Spec constraint: prompt is schema + current question only |
