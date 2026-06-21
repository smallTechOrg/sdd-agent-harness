# Architecture

This is a **structure spec**: it states contracts (WHAT the wiring is), not implementation
(HOW each function is written — that lives in `src/`). It is the single home for the
**pinned stack**, the **component topology**, the **environment-variable registry**, the
**deterministic startup sequence** (including the readiness rule), the **inter-component
contracts**, the **enumerated failure modes**, the **concurrency & retry policy**, and the
**observability contract**.

**One-fact-one-place anchors that live HERE:** the pinned versions, the env-var names, the port numbers, the failure-mode list. The `/health` response shape and `stub_mode` flag live in [api.md](api.md); `audit_log` columns live in [data-model.md](data-model.md). Do not re-define those here — link to them.

---

## Stack (pinned)

| Layer | Choice | Version pin | Rationale |
|-------|--------|-------------|-----------|
| Language | Python | >=3.12 (floor: PEP 695 generics + match stmt) | standard for ML/data tooling; async support (→ SC-CORE) |
| Package manager | uv | >=0.5 (floor: workspace lockfile) | fast installs, deterministic lock (→ constraint: Phase-1 build ceiling) |
| Web framework | FastAPI | 0.115.* | async + Pydantic v2 for /query + /datasets contracts (→ SC-CORE) |
| Settings loader | pydantic-settings | 2.* | typed env vars, `extra="ignore"` for [C-ENV-EXTRA]; see gotchas.md (→ constraint: LLM provider switch) |
| Agent framework | none — hand-rolled node loop | n/a | single-path linear graph (generate→execute→finalize) does not need LangGraph's overhead; see agent-graph.md (→ SC-CORE) |
| Analytics DB | DuckDB | 1.1.* | columnar analytics over uploaded CSV/JSON/Excel/Parquet; persistent tables not views [C-DUCKDB-VIEW] (→ constraint: Database engine analytics) |
| Metadata spine | SQLite (via aiosqlite) | aiosqlite 0.20.* | async point reads/writes for sessions, dataset registry, audit log (→ SC-7) |
| DB driver (DuckDB) | duckdb | 1.1.* | native DuckDB python driver; no SQLAlchemy needed for columnar path (→ constraint: Database engine analytics) |
| DB driver (SQLite) | aiosqlite | 0.20.* | async SQLite for metadata spine (→ SC-7) |
| File ingestion | pandas + openpyxl | pandas 2.2.*, openpyxl 3.1.* | read CSV/JSON/Excel/Parquet into DuckDB persistent tables [C-EXCEL-TMP] (→ SC-CORE) |
| Multipart upload | python-multipart | 0.0.20.* | FastAPI file upload [C-MULTIPART] (→ SC-CORE) |
| LLM provider | google-genai | 0.8.* | gemini-2.5-flash via Google Gemini API; context caching for token economy; stub fallback [C-STUB] [C-LLM-SDK] (→ SC-STUB) |
| Frontend | Next.js (App Router) | 15.x | RSC + fetch; stub-mode banner; see ui.md (→ SC-UX) |
| UI runtime | React | 19.x | Next.js 15 peer (→ SC-UX) |
| Styling | Tailwind CSS | 3.4.x | utility-first; no bespoke CSS files (→ SC-UX) |
| Markdown renderer | react-markdown + remark-gfm | react-markdown 9.x / remark-gfm 4.x | GFM tables not `<pre>` [C-MD-RENDER] (→ SC-UX) |
| Chart renderer | react-plotly.js + plotly.js | react-plotly.js 2.x / plotly.js 2.x | interactive charts; SSR-disabled [C-PLOTLY-SSR] (→ SC-UX) |
| Data fetching (frontend) | native fetch | built-in Next.js 15 | simple request/response; no streaming needed (→ SC-CORE) |
| Test runner (backend) | pytest + pytest-asyncio | pytest 8.x / pytest-asyncio 0.24.x | async FastAPI tests; ALLOW_MODEL_REQUESTS=False guard (→ SC-STUB) |
| Test runner (frontend) | Playwright | 1.46.x | Live-UI gate; rendered-DOM assertions (→ SC-UX) |

---

## Component Topology

```
Browser ── Next.js frontend (:3000)
   │  HTTP/JSON  (NEXT_PUBLIC_API_URL or http://localhost:8001)
   ▼
FastAPI backend (:8001)
   │
   ├─── in-process ──► Agent Loop (src/agent/)
   │                      │
   │                      ├─ HTTPS ──► Google Gemini API (gemini-2.5-flash)
   │                      │            [or in-process stub in stub_mode]
   │                      │
   │                      └─ file I/O ──► DuckDB (./data/app.duckdb)
   │
   └─── file I/O ──► SQLite metadata spine (./data/meta.db)
                      [sessions, dataset registry, audit_log]
```

| Component | Responsibility (one sentence, names the artefact it owns) | Source path |
|-----------|-----------------------------------------------------------|-------------|
| Next.js frontend | Renders all screens in ui.md and reads `stub_mode` from `GET /health` to display the stub banner. | `frontend/` |
| FastAPI backend | Serves every endpoint in api.md (§POST /datasets, §POST /query, §GET /datasets, §GET /sessions, §GET /health) and validates each request body. | `src/api/` |
| Agent Loop | Runs the three-node graph in agent-graph.md (`node_generate_sql` → `node_execute_sql` → `node_finalize`) producing the response for §POST /query. | `src/agent/` |
| DuckDB store | Holds the persistent dataset tables (`dataset_<id>`) ingested via §POST /datasets and queried by `node_execute_sql`. | `src/db/duckdb.py` |
| SQLite metadata spine | Stores the `session`, `dataset`, `query_run`, and `audit_log` tables in data-model.md, read/written by the API and agent loop. | `src/db/sqlite.py` |
| Gemini LLM client | Serves the NL→SQL completion call in agent-graph.md `node_generate_sql` (or its in-process stub). | `src/integrations/llm.py` |

---

## Environment Variables

| Var | Required | Default / example | Purpose / allowed values |
|-----|----------|-------------------|--------------------------|
| `DAA_LLM_PROVIDER` | yes | `stub` | switches live LLM vs canned stub; one of {`stub`, `gemini`} |
| `DAA_GEMINI_API_KEY` | conditional — if `DAA_LLM_PROVIDER=gemini` | — (secret) | Google Gemini API auth; never logged; `pydantic.SecretStr` |
| `DAA_LLM_MODEL` | no | `gemini-2.5-flash` | model id; config not hardcoded; [C-LLM-MODEL] |
| `DAA_DUCKDB_PATH` | no | `./data/app.duckdb` | DuckDB analytics file location |
| `DAA_SQLITE_PATH` | no | `./data/meta.db` | SQLite metadata spine file location |
| `DAA_PORT` | no | `8001` | API listen port (matches topology diagram) |
| `DAA_LOG_LEVEL` | no | `INFO` | log verbosity; one of {`DEBUG`,`INFO`,`WARNING`,`ERROR`} |
| `DAA_REQUEST_TIMEOUT_S` | no | `30` | per-LLM-call ceiling in seconds; matches Inter-Component Contracts |
| `DAA_MAX_RESULT_ROWS` | no | `10000` | max rows returned in a single query response |
| `DAA_MAX_UPLOAD_BYTES` | no | `209715200` | 200 MB; per-file upload limit |
| `DAA_CORS_ORIGINS` | no | `http://localhost:3000` | allowed CORS origin(s) for the frontend |
| `NEXT_PUBLIC_API_URL` | no | `http://localhost:8001` | browser-visible backend URL; [C-API-URL] |
| `ALLOW_MODEL_REQUESTS` | no | `True` | set `False` in test conftest.py to enforce offline stub [C-STUB] |
| `TRACE_INCLUDE_SENSITIVE_DATA` | no | `false` | OTel redaction flag; see harness/patterns/observability.md |

---

## Startup Sequence

1. Process launch → pydantic-settings loads all `DAA_*` vars from env; logs `settings loaded provider=<DAA_LLM_PROVIDER>`.
2. Provider resolved from `DAA_LLM_PROVIDER`; if `gemini` and `DAA_GEMINI_API_KEY` is unset → raise `ValueError("DAA_GEMINI_API_KEY required when DAA_LLM_PROVIDER=gemini")`, exit non-zero; stderr contains `DAA_GEMINI_API_KEY`.
3. Data directory created if absent (`os.makedirs("./data", exist_ok=True)`) guarding bare dirname [C-DB-DIRNAME]; logs `data dir ready`.
4. FastAPI lifespan starts → `create_tables_sqlite()` runs idempotent `CREATE TABLE IF NOT EXISTS` on the SQLite spine; DuckDB connection opened; logs `schema ready`.
5. Server binds `DAA_PORT` (default 8001) and is ready to serve; logs `listening on :8001`.
6. `GET /health` → 200 with `stub_mode` boolean (shape defined in api.md §GET /health). Before step 4 completes, `GET /health` → 503.

**Acceptance criterion 1 (refuse-to-start, EARS — Unwanted):**
> **P1-AC6** — IF `DAA_LLM_PROVIDER=gemini` AND `DAA_GEMINI_API_KEY` is unset, THEN the server SHALL refuse to start and exit non-zero with stderr containing `DAA_GEMINI_API_KEY`. (→ SC-5)
> **Test:** `DAA_LLM_PROVIDER=gemini uv run uvicorn src.api.main:app` — `assert process.returncode != 0 and "DAA_GEMINI_API_KEY" in stderr`.

**Acceptance criterion 2 (readiness-before-bootstrap, EARS — Unwanted) — REQUIRED:**
> **P1-AC7** — WHILE `create_tables_sqlite()` has not completed, `GET /health` SHALL return 503 (not 200), so no request is served against an absent schema. (→ SC-5)
> **Test:** start the app with bootstrap delayed by a monkeypatched sleep; `assert GET /health` returns 503 before `schema ready` is logged and 200 after.

---

## Inter-Component Contracts

| Caller | Callee | Transport | Timeout (s) | Retry policy `(count, base_ms, cap_ms, jitter)` or `no retry` | On failure (concrete) |
|--------|--------|-----------|-------------|---------------------------------------------------------------|-----------------------|
| Browser | FastAPI backend | HTTP/JSON | 30 | no retry (browser handles user retry) | error toast in UI (ui.md Error state); keep user input |
| FastAPI API layer | Agent Loop | in-process | 30 | no retry (agent is idempotent per run) | HTTP 500 + `request_id` logged; no partial audit write |
| Agent Loop `node_generate_sql` | Google Gemini API | HTTPS | 30 | (2, 250, 4000, yes) | `asyncio.TimeoutError` → set `state.error`; route to `node_handle_error` |
| Agent Loop `node_execute_sql` | DuckDB | file I/O | 5 | (3, 100, 2000, no) | `duckdb.OperationalError` → after retries set `state.error`; route to `node_handle_error` |
| FastAPI API layer | SQLite spine | file I/O | 5 | (3, 100, 2000, no) | after retries → HTTP 503 with `error.code="DB_UNAVAILABLE"` |

---

## Failure Modes

| Failure | Detection (named exception / observable signal) | Recovery (concrete → REAL PN-ACn in delivery-plan.md) |
|---------|-------------------------------------------------|--------------------------------------------------------|
| LLM call timeout | `asyncio.TimeoutError` after `DAA_REQUEST_TIMEOUT_S` | `state.error` set; `node_handle_error` writes audit row; API returns 504 with `error.code="LLM_TIMEOUT"` (→ P1-AC8) |
| LLM non-2xx response | `google.genai.errors.APIError` (HTTP 4xx/5xx from Google) | (2, 250, 4000, yes) retry; on exhaustion set `state.error`; API returns 502 with `error.code="LLM_ERROR"` (→ P1-AC8) |
| Malformed model output (non-SQL or non-SELECT) | `ValueError` in guard predicate `sql.strip().upper().startswith("SELECT")` | `state.error` set; API returns 422 with `error.code="BAD_SQL"`; 0 audit `sql` rows written (→ P1-AC9) |
| SQL execution error (bad SQL past guard) | `duckdb.Error` subclass during `execute()` | retry per policy; on exhaustion set `state.error`; API returns 422 with `error.code="QUERY_ERROR"` (→ P2-AC5) |
| DuckDB file unavailable / locked | `duckdb.IOException` / `duckdb.OperationalError` | retry (3, 100, 2000, no); after retries HTTP 503 with `error.code="DB_UNAVAILABLE"` (→ P1-AC7) |
| SQLite spine unavailable | `aiosqlite.OperationalError` / `"database is locked"` | retry (3, 100, 2000, no); after retries HTTP 503 with `error.code="DB_UNAVAILABLE"` (→ P1-AC7) |
| Missing key in live mode | `ValueError` at startup (step 2 above) | server refuses to start; stderr contains `DAA_GEMINI_API_KEY`; exit non-zero (→ P1-AC6) |
| Upload too large / wrong type | HTTP 413 from FastAPI / `pydantic.ValidationError` | API returns 422 with `error.code="UNSUPPORTED_FILE"` or 413; no DuckDB write (→ P1-AC5) |
| Excel temp file leak | `tempfile.mkdtemp()` directory not cleaned | use `contextlib.ExitStack` + `shutil.rmtree` in a `finally` block [C-EXCEL-TMP] (→ P2-AC6) |

---

## Concurrency & Retry Policy

| Concern | Decision | Notes |
|---------|----------|-------|
| Writer model | single-writer per DuckDB connection; SQLite aiosqlite uses one async connection with WAL mode | single-tenant local app; the DB-locked failure mode fires after lock-acquire timeout |
| Lock-acquire timeout (s) | 5 s | how long a writer waits before `duckdb.IOException` / `aiosqlite.OperationalError` fires |
| Max concurrent in-flight requests | 1 (single-tenant local; FastAPI default worker) | ties to vision.md Hard Constraints concurrency envelope |
| Restart safety (idempotent process start) | `CREATE TABLE IF NOT EXISTS` on SQLite; DuckDB persistent tables are file-backed; a restart with partial write → schema is no-op; no data truncation | second start with partial-write DuckDB file re-opens the existing file safely |

**Standard retry policy** (referenced by Inter-Component Contracts + Failure Modes — define ONCE here):

> Default: `(count, base_ms, cap_ms, jitter)` = `(3, 100, 2000, no)`. Backoff is exponential `base_ms * 2^attempt` capped at `cap_ms`; jitter is disabled (deterministic for tests). Non-idempotent calls use `no retry` unless explicitly listed. LLM calls use `(2, 250, 4000, yes)` (full-jitter) because retries on a 429 need spread.

---

## Observability

| Aspect | Contract |
|--------|----------|
| Request-id format | UUIDv4 string, generated at the FastAPI edge per request if absent in `X-Request-Id` header |
| Request-id propagation | Carried as `X-Request-Id` on HTTP/JSON edges (Browser↔API); passed as `run_id` field into agent state (in-process); included in every `audit_log` row in data-model.md §audit_log |
| Per-failure log fields | Every Failure Modes row logs `{request_id, failure_name, exc_type, action_taken}` at ERROR level; failures that write an audit row also persist `request_id` to `audit_log.run_id` (data-model.md §audit_log) |
| Log level source | `DAA_LOG_LEVEL` env var (see Environment Variables) |
| OTel GenAI attributes | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` logged per LLM call and mirrored in `audit_log` OTel columns (data-model.md §audit_log) |
| Redaction | `TRACE_INCLUDE_SENSITIVE_DATA=false` redacts `audit_log.payload` from traces (harness/patterns/observability.md) |

---

## Phase Notes (architecture deltas per phase)

| Phase | Components REAL | Components STUBBED (correct shape) | Contract frozen for later swap |
|-------|-----------------|-------------------------------------|-------------------------------|
| P1 | Next.js frontend shell + FastAPI (/health, /datasets POST GET, /sessions, /query) + SQLite spine | Agent Loop (canned deterministic stub response); DuckDB (in-process; dataset table created, stub SQL executed) | api.md §POST /query → Response 200 (schema byte-identical at P2 swap; only values change) |
| P2 | + Agent Loop live (real Gemini gemini-2.5-flash call) + DuckDB live analytics queries + audit_log writes | — | data-model.md §audit_log (columns frozen at P1 schema; Phase 2 writes real rows) |
| P3 | + Analyst workflow (suggestions, hypotheses, executive summary) + dataset delete + dashboard PIN (Phase 3) | — | api.md §POST /query → Response 200 (suggestions array frozen at P1 schema shape; Phase 3 fills with real content) |
