# Phase 1 Plan — Data Analyst Agent

**Phase:** Phase 1 — Shaped First Release
**Criteria:** P1-AC1 through P1-AC11 (spec/delivery-plan.md §Phase 1)
**Session log:** logs/sessions/2026-06-22-045955-v2.md
**Status:** in-progress

---

## Recipe Inventory (what the python-fastapi-duckdb recipe already ships vs. the delta)

| Capability | Recipe ships? | Delta action |
|------------|---------------|--------------|
| FastAPI app factory + lifespan | yes | keep; rename APPNAME→DAA, port 8000→8001 |
| GET /health with stub_mode | yes | keep; adapt env-prefix |
| pydantic-settings + SecretStr | yes | keep; swap prefix, add DAA_GEMINI_API_KEY |
| SQLite spine (via SQLAlchemy async) | yes, but wrong driver | REPLACE with aiosqlite (spec requires aiosqlite 0.20.*); drop SQLAlchemy entirely |
| DuckDB connection + persistent table | yes (generic event-store seam) | REPLACE with dataset_<id> ingest pattern |
| LangGraph ReAct loop | yes | REPLACE with hand-rolled 3-node loop (architecture.md: "none — hand-rolled") |
| Anthropic LLM client | yes | REPLACE with google-genai stub (Phase 1 stub-only; gemini path wired but not called) |
| Jinja2 templates / UI | yes | REPLACE with Next.js 15 frontend in frontend/ dir |
| Stub LLM (no key, no network) | yes | keep pattern; emit canned 5-row response for POST /query |
| pytest conftest + ALLOW_MODEL_REQUESTS | yes | keep; adapt to new test paths |
| CORS config | yes | keep; default DAA_CORS_ORIGINS=http://localhost:3000 |

**Net: the recipe provides the skeleton shape but requires ~60% replacement to match the spec stack. Steps cover the deltas only.**

---

## Step DAG

| Step | Deliverable | Gate command (< 30 s) | Depends on | Parallel with |
|------|-------------|----------------------|------------|---------------|
| 0 | Scaffold: copy recipe to project root, rename APPNAME→DAA, swap SQLAlchemy→aiosqlite, swap LangGraph→hand-rolled stub, swap Anthropic→google-genai stub, port→8001; `GET /health` returns `{"status":"ok","stub_mode":true}` | `DAA_LLM_PROVIDER=stub uv run uvicorn src.api.main:app --port 8001 &; sleep 2; curl -sf http://localhost:8001/health \| python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok' and d['stub_mode']==True"` | none | none (blocks all) |
| 1 | SQLite spine: `create_tables_sqlite()` idempotent DDL for all five tables — session, dataset, query_run, conversation_message, audit_log — with all indexes from data-model.md; readiness probe returns 503 before bootstrap, 200 after | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest tests/test_startup.py -q` | Step 0 | Step 4 (frontend) |
| 2A | POST /datasets + GET /datasets: multipart upload, pandas ingest CSV/JSON/Excel/Parquet into DuckDB persistent table `dataset_<id>`, SQLite registry row written; GET /datasets returns dataset card with row_count; 422 UNSUPPORTED_FILE + 413 FILE_TOO_LARGE guards; fixture `tests/fixtures/sample.csv` (100 rows) and `tests/fixtures/broken.png` created | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest tests/test_datasets.py -q` | Step 1 | Step 2B |
| 2B | POST /sessions + GET /sessions: create session → 201 + Location header + uuid4 id; list sessions; SQLite reads/writes via aiosqlite; empty question + invalid session_id → 422 BAD_INPUT | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest tests/test_sessions.py tests/test_health.py -q` | Step 1 | Step 2A |
| 3 | POST /query stub: validate session_id + dataset_ids exist, reject empty question (422 BAD_INPUT), return deterministic 5-row response (rows[0]["product"]=="Widget A", sql starts with SELECT, chart_spec.layout.xaxis.title=="product", 2 suggestion strings), write exactly 1 audit_log row with action='llm' and duration_ms>=0 | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest tests/test_query.py tests/test_audit.py -q` | Steps 2A + 2B | none |
| 4 | Next.js 15 frontend shell: top nav "Data Analyst Agent", session sidebar with active highlight + "+ New" button, Datasets tab (upload dropzone), Query tab (textarea + submit, result table placeholder, Plotly chart placeholder, suggestion chip placeholders), error-toast region, stub banner reading exactly `STUB MODE — responses are canned, not real AI output` on first paint — all UI components present, `npm run build` exits 0 | `cd frontend && npm run build 2>&1 \| tail -5 && echo BUILD_OK` | Step 0 | Steps 1, 2A, 2B, 3 (independent path) |
| 5 | Wire frontend to backend: fetch GET /health to drive banner visibility, POST /sessions on tab open, GET /sessions for sidebar, POST /datasets for upload with dataset card render (name + row_count), POST /query stub call with GFM table render (react-markdown + remark-gfm), Plotly chart render (SSR-disabled), suggestion chip click fills textarea + auto-submits; Playwright e2e tests pass for banner and sidebar | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest tests/test_startup.py::test_refuse_to_start_without_key -q && cd frontend && npx playwright test tests/e2e/test_banner.py tests/e2e/test_sidebar.py --reporter=line` | Steps 3 + 4 | none |

### DAG diagram

```
Step 0  scaffold ──────────────────────────────────────────────────────► Step 4  (frontend shell — independent)
    │                                                                          │
    ▼                                                                          │
Step 1  SQLite spine ─────┬──────────────────────────┐                        │
                          │                          │                        │
                          ▼                          ▼                        │
                    Step 2A  /datasets         Step 2B  /sessions             │
                          │                          │                        │
                          └──────────┬───────────────┘                        │
                                     ▼                                        │
                               Step 3  POST /query stub                       │
                                     │                                        │
                                     └───────────────────────────────────────►┤
                                                                              ▼
                                                                        Step 5  wire + e2e
```

**Critical path:** 0 → 1 → 2A (or 2B) → 3 → 5 (5 sequential steps; Step 4 runs in parallel after Step 0).
**Maximum parallel front:** Steps 2A and 2B run simultaneously; Step 4 runs alongside Steps 1, 2A, 2B, 3.

---

## Progress Tracker

| Step | Owner | Status | Gate | Notes |
|------|-------|--------|------|-------|
| 0 — Scaffold | executor | green | `curl /health → {"status":"ok","stub_mode":true}` GATE PASS | pyproject.toml + src/ + tests/conftest.py written; gate passed; committed 6d95d1a |
| 1 — SQLite spine | executor | green | `pytest tests/test_startup.py -q` exits 0 — 3 passed | five tables + indexes; readiness 503/200 probe; P1-AC7; committed |
| 2A — /datasets | executor | green | `pytest tests/test_datasets.py -q` — 5 passed | sample.csv (100 rows, 3 cols), broken.png fixtures; DuckDB persistent TABLE [C-DUCKDB-VIEW]; P1-AC4, P1-AC5 |
| 2B — /sessions | executor | green | `pytest tests/test_sessions.py tests/test_health.py -q` exits 0 — 4 passed | uuid4 id, 201 + Location; P1-AC2, P1-AC10; committed |
| 3 — POST /query stub | executor | todo | `pytest tests/test_query.py tests/test_audit.py -q` exits 0 | canned 5-row response; 1 audit_log row; P1-AC3, P1-AC8, P1-AC9 |
| 4 — Next.js shell | executor | green | `npm run build` exits 0 — GATE PASS | stub banner literal; session sidebar; Datasets + Query tabs; Plotly SSR-disabled; P1-AC1, P1-AC11 |
| 5 — Wire + e2e | executor | todo | playwright tests pass; refuse-to-start test passes | GET /health → banner; POST /sessions per tab; chip auto-submit; P1-AC1, P1-AC6, P1-AC11 |

---

## Phase Acceptance

All criteria from spec/delivery-plan.md §Phase 1 (c) — all unchecked at start.

| id | EARS summary | Acceptance test | Status |
|----|--------------|-----------------|--------|
| P1-AC1 | WHILE stub_mode true, full-width top banner reads exactly `STUB MODE — responses are canned, not real AI output` on every screen first paint | `playwright tests/e2e/test_banner.py::test_stub_banner` | [ ] |
| P1-AC2 | WHILE DAA_LLM_PROVIDER=stub, GET /health returns 200 `{"status":"ok","stub_mode":true}` with no network call | `pytest tests/test_health.py::test_health_stub_offline` (ALLOW_MODEL_REQUESTS=False) | [ ] |
| P1-AC3 | WHEN POST /query called stub mode with valid session_id + dataset_ids, returns 200 with rows length==5, sql starts with SELECT, chart_spec.layout.xaxis.title=="product" | `pytest tests/test_query.py::test_stub_query` | [ ] |
| P1-AC4 | WHEN CSV 100 rows uploaded, GET /datasets returns dataset with name=="sample.csv", row_count==100, file_format=="csv" | `pytest tests/test_datasets.py::test_upload_and_list` | [ ] |
| P1-AC5 | IF unsupported file type uploaded, POST /datasets returns 422 with error.code=="UNSUPPORTED_FILE" and 0 DuckDB rows | `pytest tests/test_datasets.py::test_upload_unsupported_file` | [ ] |
| P1-AC6 | IF DAA_LLM_PROVIDER=gemini AND DAA_GEMINI_API_KEY unset, server refuses to start exit non-zero with stderr containing `DAA_GEMINI_API_KEY` | `pytest tests/test_startup.py::test_refuse_to_start_without_key` | [ ] |
| P1-AC7 | WHILE create_tables_sqlite() not completed, GET /health returns 503 | `pytest tests/test_startup.py::test_readiness_probe` | [ ] |
| P1-AC8 | IF stub LLM active and POST /query called, writes exactly 1 audit_log row with action=='llm' and duration_ms>=0 | `pytest tests/test_audit.py::test_stub_llm_audit_row` | [ ] |
| P1-AC9 | IF POST /query called with empty question, returns 422 with error.code=="BAD_INPUT" and UI shows error text | `pytest tests/test_query.py::test_empty_question` | [ ] |
| P1-AC10 | WHEN POST /sessions called, returns 201 with uuid4 id and Location header; GET /sessions lists it | `pytest tests/test_sessions.py::test_create_and_list_session` | [ ] |
| P1-AC11 | WHILE session active in UI sidebar, active item has bg-blue-100 CSS class and sidebar shows "+ New" button | `playwright tests/e2e/test_sidebar.py::test_active_session_highlight` | [ ] |

### Hard gates (all must be green before phase is accepted)

| Gate | Green when |
|------|------------|
| Offline stub | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest` exits 0 |
| Live-server (backend) | `uv run uvicorn src.api.main:app --port 8001` starts; `curl :8001/health` → 200 with stub_mode:true |
| Live-UI (frontend) | `cd frontend && npm run start`; `curl :3000/` → 200 with banner string in HTML |
| Stub banner | verbatim `STUB MODE — responses are canned, not real AI output` in rendered DOM at first paint |
| Golden-path smoke | delivery-plan.md §(b) demo script steps 1–11 run end-to-end; step 8 asserts row_count==5 + chart axis titles |
| Production driver | tests run against `./data/app.duckdb` and `./data/meta.db` (not in-memory substitutes) [C-DB-SAME-AS-PROD] |
| README current | every command in quickstart works verbatim from repo root |
