# Tech Stack

## Stack Decisions

### Language / Runtime

| Concern | Choice | Reason |
|---------|--------|--------|
| Backend language | Python 3.12+ | User-stated constraint. Excellent DuckDB and Gemini SDK support; matches data-processing idioms. |
| Frontend language | TypeScript (Next.js 15 / React 19) | User-stated constraint. Type safety surfaces API contract mismatches at build time. |
| Dependency management — Python | `uv` | User-stated constraint. 10–100x faster than pip; lockfile reproducibility. |
| Dependency management — TypeScript | `pnpm` | User-stated constraint. Disk-efficient, deterministic lockfile. |

### LLM

| Concern | Choice | Reason |
|---------|--------|--------|
| LLM provider | Gemini (Google AI Studio) | User-stated constraint; key supplied as `GEMINI_API_KEY`. |
| Gemini client library | `google-generativeai` | Official Python SDK from Google; direct support for `generate_content`; no extra abstraction needed for a single synchronous call per query turn. |
| Default model | `gemini-2.5-flash` | Current default per tech-stack.md LLM Model Name Rule. Configurable via `ANALYST_LLM_MODEL` env var. |
| Prompt strategy | Schema-only: system instruction + column names/types + user question | Enforced in spec; keeps token cost minimal and prevents PII leakage via row data. Never send conversation history to Gemini. |
| Stub strategy | `GEMINI_API_KEY` absent or empty → `StubGeminiClient` returns a hardcoded SELECT statement tagged with `<!-- stub-nl-query -->` | Satisfies Phase 2 offline requirement and ai-agents.md rule 7 (stub visibly labelled). Provider resolution is automatic — no extra flag needed. |

### Databases / Persistence

| Concern | Choice | Reason |
|---------|--------|--------|
| Analytical query engine | `duckdb` Python package (v1.x, official) | User-stated constraint. In-process, zero-config; reads CSV/JSON files natively by absolute path; no separate server process required. |
| Session metadata + audit log | SQLite via `SQLAlchemy 2.0` + `Alembic` | User-stated constraint (SQLite for session/audit metadata). SQLAlchemy typed models (`Mapped` API) + Alembic repeatable migrations = production-grade for single-server deployment. Driver (`aiosqlite` for async or `sqlite3` sync via `sqlalchemy`) declared in `[project.dependencies]`, not dev-only. |
| Session state (datasets + conversation) | JSONB column (`TEXT` + Python `json`) on the `sessions` SQLite table | Keeps all session data in one row; avoids a separate JSON-on-filesystem approach while still using SQLite as user-stated. Simpler than a separate sessions directory and queryable. |
| Audit log | Separate `audit_log` SQLite table in the same `data/app.db` | Collocating with session store avoids a second file format; append-only by application convention (no UPDATE/DELETE). |
| Dataset files | Local filesystem under `data/datasets/<session_id>/` | User-stated constraint; DuckDB reads files directly by path — no in-memory import. |
| SQLite file location | `data/app.db` (path configurable via `ANALYST_DATABASE_URL`) | Single file, easy to back up, zero setup. |

### API / Server

| Concern | Choice | Reason |
|---------|--------|--------|
| HTTP framework | FastAPI (latest stable) | User-stated constraint. Async-capable, auto-generates OpenAPI docs, native Pydantic integration. |
| ASGI server | `uvicorn` | Standard for FastAPI; lightweight; single-worker sufficient for single-user deployment. |
| Default dev port | `8001` | Permanent rule in tech-stack.md — port 8000 commonly occupied. |
| Session cookies | `starlette.middleware.sessions.SessionMiddleware` | Starlette is FastAPI's transport layer — zero extra dependency. Stores only the session ID UUID in a signed cookie; all state remains server-side in SQLite. Cookie is `HttpOnly; SameSite=Strict`. |
| CORS | `fastapi.middleware.cors.CORSMiddleware` | Needed for Next.js dev server (different port); locked to `localhost` origins. |
| File upload | `fastapi.UploadFile` + `python-multipart` | Native FastAPI multipart; size check before writing to disk. |

### Frontend

| Concern | Choice | Reason |
|---------|--------|--------|
| Framework | Next.js 15 (App Router) + React 19 | User-stated constraint. App Router gives layouts and client components for chat state. |
| HTTP client | Native `fetch` (browser) | No extra dependency; ships in all modern runtimes; avoids axios version conflicts with Next.js internals. |
| Table rendering | Native HTML `<table>` with React pagination state (`useState`) | The spec requires exactly 25-rows/page, Previous/Next controls, and right-align for numerics — achievable with a small hook. A library (TanStack Table) would add bundle weight for a feature subset; plain HTML is testable and accessible. |
| State management | React built-in (`useState`, `useEffect`, context if needed) | Single-page, single-session; no cross-route state sharing needed; Redux/Zustand is overkill. |
| Styling | Tailwind CSS v4 | Utility-first; no separate stylesheet build step in Next.js 15; consistent spacing and colour tokens. |

### Testing

| Concern | Choice | Reason |
|---------|--------|--------|
| Python test runner | `pytest` + `pytest-asyncio` | Standard; fixture system maps cleanly to session/DB setup and teardown. |
| Backend HTTP testing | `httpx` + `fastapi.testclient.TestClient` | `TestClient` wraps ASGI in a synchronous context; same DB driver as production. |
| Frontend test runner | `vitest` | Vite-native; works inside Next.js projects without configuration gymnastics; faster than Jest. |
| Frontend component tests | `@testing-library/react` | Behaviour-focused; asserts what the user sees, not implementation details. |
| Coverage | `pytest-cov` (Python) | Integrates with pytest. |

### Observability

| Concern | Choice | Reason |
|---------|--------|--------|
| Structured logging | `structlog` | JSON-formatted output; trace_id propagation; minimal config. |
| Log level | `ANALYST_LOG_LEVEL` env var (default `INFO`) | Switchable without code changes. |

---

## Directory Layout

```
<repo root>
├── src/
│   └── analyst/                        ← Python package (slug = analyst)
│       ├── __init__.py                 ← __version__ = "0.1.0"
│       ├── api/
│       │   ├── __init__.py             ← create_app() factory + lifespan
│       │   ├── _common.py              ← ok(), api_error()
│       │   ├── health.py               ← GET /health
│       │   ├── sessions.py             ← POST /api/sessions, GET /api/sessions/current
│       │   ├── datasets.py             ← POST /api/datasets
│       │   ├── query.py                ← POST /api/query
│       │   └── audit.py                ← GET /api/audit
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py             ← BaseSettings (env prefix ANALYST_)
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py               ← SQLAlchemy: SessionRow, AuditLogRow
│       │   └── session.py              ← engine, sessionmaker, get_session, init_db
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── session.py              ← Pydantic: Session, DatasetMeta, ColumnDef, ConversationTurn
│       │   └── audit.py                ← Pydantic: AuditLogEntry
│       ├── services/
│       │   ├── __init__.py
│       │   ├── session_store.py        ← read/write Session blobs in SQLite
│       │   ├── dataset_service.py      ← infer schema, write file, update session
│       │   ├── nl_query.py             ← build prompt, call Gemini client, validate SQL
│       │   ├── query_engine.py         ← DuckDB execution, 1000-row cap, 30s timeout
│       │   └── audit_service.py        ← append AuditLogRow to SQLite
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py                 ← GeminiProvider protocol (abstract)
│       │   ├── gemini_client.py        ← real google-generativeai call
│       │   └── stub_client.py          ← hardcoded SELECT + <!-- stub-nl-query --> tag
│       └── prompts/
│           └── nl_to_sql.md            ← system instruction template
├── frontend/                           ← Next.js project root
│   ├── src/
│   │   └── app/
│   │       ├── layout.tsx              ← root layout; stub banner slot
│   │       ├── page.tsx                ← main two-panel view
│   │       └── components/
│   │           ├── DatasetSidebar.tsx
│   │           ├── ChatPanel.tsx
│   │           ├── ChatInput.tsx
│   │           ├── ResultTable.tsx     ← paginated HTML table, 25 rows/page
│   │           ├── StubBanner.tsx      ← amber banner when GEMINI_API_KEY absent
│   │           └── SqlCollapsible.tsx
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── vitest.config.ts
├── tests/
│   ├── conftest.py                     ← settings singleton reset + SQLite test DB fixture
│   ├── unit/
│   │   ├── test_smoke.py
│   │   ├── domain/test_models.py
│   │   ├── services/test_dataset_service.py
│   │   ├── services/test_nl_query.py
│   │   └── services/test_query_engine.py
│   └── integration/
│       └── test_pipeline.py            ← golden-path TestClient smoke test
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_initial.py
├── data/                               ← runtime data (gitignored)
│   ├── datasets/                       ← uploaded files per session
│   └── app.db                          ← SQLite database
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANALYST_DATABASE_URL` | Yes | — | `sqlite:///data/app.db` for local dev |
| `GEMINI_API_KEY` | No | `""` | Absent/empty → stub mode; UI banner shown |
| `ANALYST_LLM_MODEL` | No | `gemini-2.5-flash` | Gemini model ID; configurable without redeployment |
| `ANALYST_DATA_DIR` | No | `data` | Root directory for dataset files |
| `ANALYST_LOG_LEVEL` | No | `INFO` | structlog level |
| `ANALYST_MAX_UPLOAD_MB` | No | `50` | Upload size ceiling |
| `ANALYST_MAX_RESULT_ROWS` | No | `1000` | Result set cap before truncation |
| `ANALYST_QUERY_TIMEOUT_S` | No | `30` | DuckDB query timeout in seconds |
| `ANALYST_SECRET_KEY` | Yes | — | Starlette session middleware signing key |

---

## Key Libraries (pyproject.toml `[project.dependencies]`)

| Library | Purpose |
|---------|---------|
| `fastapi` | HTTP framework |
| `uvicorn[standard]` | ASGI server |
| `python-multipart` | Multipart file upload parsing (required by FastAPI) |
| `sqlalchemy>=2.0` | ORM + session management |
| `alembic` | Database migrations |
| `aiosqlite` | Async SQLite driver (SQLAlchemy async mode) |
| `pydantic>=2.0` | Domain models + request/response validation |
| `pydantic-settings` | Settings from env vars + `.env` file |
| `google-generativeai` | Gemini API client |
| `duckdb>=1.0` | Embedded analytical query engine |
| `structlog` | Structured logging |
| `python-dotenv` | `.env` file loading |

Dev dependencies (`[dependency-groups.dev]`):
`pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`

---

## What to Avoid

| Anti-pattern | Reason |
|--------------|--------|
| Sending row data to Gemini | Spec constraint; PII risk; token cost. Schema only. |
| DML/DDL execution in DuckDB | Attack surface. Validate SELECT-only before execution — twice (nl-query + query-engine). |
| Raw `sqlite3` / manual migrations | Alembic ensures repeatable, reviewable schema changes. |
| Storing `GEMINI_API_KEY` in the session or audit log | Security. Key stays in env only. |
| LangGraph or any agent framework | No multi-step reasoning in Phase 1; a single synchronous Gemini call is sufficient and simpler. |
| Storing conversation history in the Gemini prompt | Spec constraint; prompt must be schema + current question only. |
| `axios` on the frontend | `fetch` is sufficient; avoids an extra dependency. |
| TanStack Table or any React table library | Spec table requirements are met by plain HTML + pagination state hook. |

---

## Permanent Rules (from boilerplate — apply to this project)

- Default dev port: **8001** (not 8000).
- LLM model name: **`gemini-2.5-flash`** — configurable via `ANALYST_LLM_MODEL`.
- DB driver (`aiosqlite`) must be in `[project.dependencies]`, not dev-only.
- Tests use the same DB driver as production (SQLite via aiosqlite — not a substitute, it IS the production driver here).
- `extra="ignore"` in `pydantic-settings` `model_config`.

---

## Phase Gate Commands

| Phase | Exact gate command | Passes when |
|-------|-------------------|-------------|
| 1 | `uv run alembic upgrade head && uv run alembic current && uv run pytest tests/unit/ -v` | `alembic current` shows a revision hash (not blank); all unit tests green |
| 2 | `GEMINI_API_KEY="" uv run pytest tests/ -v` | Full suite passes with no Gemini key; golden-path TestClient smoke test green; stub banner text asserted in response body |
| 2 (live smoke) | `uv run uvicorn analyst.api:app --port 8001 & sleep 2 && curl -sf http://localhost:8001/health && curl -sf -c /tmp/da-cookies.txt http://localhost:8001/api/sessions/current \| python3 -m json.tool` | Both curl calls exit 0 with valid JSON bodies |
| 3 | `GEMINI_API_KEY=<real-key> uv run pytest tests/ -v` | All tests pass with a real Gemini key; end-to-end query resolves against a test CSV |
| 4 | `pnpm --prefix frontend test run && pnpm --prefix frontend build` | Vitest green; Next.js production build succeeds with no type errors |
