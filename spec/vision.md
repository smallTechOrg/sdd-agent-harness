# Vision — Product Definition & Contract of Intent

---

## Product Definition

A browser application for a solo data analyst. The analyst uploads one or more tabular files (CSV, JSON, Excel `.xlsx`, or Parquet, ≤ 200 MB each) and asks a question as a natural-language English string. The system is an agentic data analyst: it translates the question to a read-only SQL query using Gemini gemini-2.5-flash (Google Gemini API), executes it against the uploaded data in a local DuckDB file, and returns the result as a Markdown table rendered to a sortable HTML grid plus an interactive Plotly chart (bar, line, or scatter selected by data shape). Every SQL execution and LLM call is appended to an audit log. Sessions and the dataset registry survive server restarts via a SQLite spine.

**In one sentence:**
> A local browser tool that lets a data analyst upload CSV / JSON / Excel / Parquet files, ask natural-language questions, and receive the answer as a Markdown table and interactive Plotly chart — powered by gemini-2.5-flash translating the question to DuckDB SQL.

### Input contract

Full input shape: spec/api.md §POST /query

### Output contract

Full output shape: spec/api.md §POST /query

---

## Users & Jobs

| User | Role (concrete, not an adjective) | Primary job (verb-first task) | Success signal (measurable → SC) |
|------|-----------------------------------|-------------------------------|----------------------------------|
| Analyst | Solo data analyst; no production SQL environment; works locally on their laptop | Upload a tabular dataset and answer an ad-hoc business question without writing SQL | Correct answer table (≥ 1 row) plus a Plotly chart with axis labels renders in < 10 s without writing SQL (→ SC-CORE, SC-UX) |

---

## Problem & Current Baseline

Today the analyst pastes a CSV into a spreadsheet, writes pivot tables or hand-crafts SQL in a local client, and interprets results manually. Each non-trivial question takes roughly 15 minutes and carries an [ASSUMPTION: ~20% error rate — user-stated] because formula errors and copy-paste mistakes are common. This product replaces the manual SQL/pivot step with a natural-language query path backed by verifiable, logged SQL.

| Axis | Before (current, quantified) | After (target, quantified) | Source class |
|------|------------------------------|----------------------------|--------------|
| Time per question | ~15 min/question (manual pivot + SQL) | < 10 s/question (p95 end-to-end) | user-stated |
| Error rate | ~20% formula/copy-paste error | 0% (SQL-verified, deterministic) | user-stated |
| Setup cost | $0 but ~15 min/session to load data | < 30 s to upload a file and start querying | user-stated |

---

## Success Criteria (EARS)

| # | EARS statement (one EARS form, with a quantity + a contract cite) | Acceptance test (location + parseable assertion) |
|---|-------------------------------------------------------------------|---------------------------------------------------|
| SC-CORE | WHEN a natural-language question is submitted against an uploaded dataset with ≥ 1 matching row, the API SHALL return a JSON object with `rows` length ≥ 1 and a non-empty `sql` string (api.md §POST /query → Response 200). | `pytest tests/test_query.py::test_top5_returns_rows` — `assert len(r.json()["rows"]) >= 1 and r.json()["sql"] != ""` |
| SC-UX | WHEN a query returns numeric data, the UI SHALL render a Plotly chart with non-empty x-axis title, non-empty y-axis title, hover tooltips, and a PNG-download modebar button (api.md §POST /query → Response 200 `chart_spec`). | Submit "revenue by category" with seeded CSV; `assert document.querySelectorAll(".modebar").length >= 1` and both axis title nodes are non-empty strings. |
| SC-STUB | IF `DAA_LLM_PROVIDER=stub` THEN the system SHALL pass the full unit test suite with no API key set and no network calls, and `GET /health` SHALL return `{"status":"ok","stub_mode":true}` (api.md §GET /health). | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest` — `assert exit_code == 0` |
| SC-FAIL | IF a submitted question produces invalid or non-SELECT SQL, THEN the API SHALL return HTTP 422 with `error.code == "BAD_SQL"` and write exactly 0 `audit_log` rows with `action='sql'` for that run (api.md §POST /query errors; data-model.md §audit_log). | `pytest tests/test_query.py::test_bad_sql` — `assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_SQL"` |
| SC-5 | WHEN the server starts with `DAA_LLM_PROVIDER=gemini` and `DAA_GEMINI_API_KEY` unset, THEN the server SHALL refuse to start and exit non-zero with stderr containing `DAA_GEMINI_API_KEY` (architecture.md Startup Sequence). | `DAA_LLM_PROVIDER=gemini uv run uvicorn src.api.main:app` — `assert process.returncode != 0 and "DAA_GEMINI_API_KEY" in stderr` |
| SC-6 | WHEN a SQL query executes successfully, the system SHALL append exactly 1 `audit_log` row with `action='sql'`, a non-empty `payload` (the SQL text), and `duration_ms >= 0` (data-model.md §audit_log). | `pytest tests/test_audit.py::test_sql_logged` — `assert count_after - count_before == 1 and row.duration_ms >= 0 and row.payload != ""` |
| SC-7 | WHILE a session exists after a server restart, the session record, dataset registry, and conversation history SHALL be retrievable from the SQLite spine (data-model.md §session, §dataset). | `pytest tests/test_persistence.py::test_session_survives_restart` — `assert r.json()["session_id"] == original_id and len(r.json()["datasets"]) >= 1` |
| SC-8 | WHERE Phase 3 analyst-workflow features are active, WHEN a query returns ≥ 1 row, the response SHALL include ≥ 2 follow-up suggestion strings each referencing a column name from the result (api.md §POST /query → Response 200 `suggestions`). | `pytest tests/test_workflow.py::test_followup_suggestions` — `assert len(r.json()["suggestions"]) >= 2 and any(col in s for col in r.json()["columns"] for s in r.json()["suggestions"])` |

---

## Non-Scope

| Excluded capability | Disposition |
|---------------------|-------------|
| Multi-user auth / RBAC | never — single-tenant local tool by design |
| Real-time collaborative editing | never — out of product thesis |
| Mobile-responsive layout | never — desktop-only local tool by design |
| Cloud / hosted deployment | never — local-only; Render only on explicit user request |
| Saved / pinned dashboards (persisted named views) | → Phase 3 |
| Dataset deletion via UI | → Phase 3 |
| Export to Excel / PDF | → Phase 3 |
| Streaming token-by-token responses | never — whole-response delivery; latency is ≤ 10 s p95 |
| Multi-tenant session isolation | never — single-user local by design |
| LLM provider switchability beyond stub/gemini | never for v1 — Google Gemini is the only live provider |

---

## Hard Constraints

| Constraint | Value |
|------------|--------|
| Phase-1 build ceiling | ≤ 30 min (hard ceiling); UI shell present with stub banner; data paths stubbed with correct shape |
| Backend port | :8001 |
| Frontend port | :3000 |
| Deploy target | local demo; Render only on explicit user request |
| Database engine (analytics) | DuckDB `1.1.*`, local file `./data/app.duckdb` — NO server DB |
| Database engine (metadata spine) | SQLite `3.45.*` (via `aiosqlite 0.20.*`), local file `./data/meta.db` — NO server DB |
| LLM provider switch | `DAA_LLM_PROVIDER` ∈ {`stub`, `gemini`}; `stub` ⇒ no key, no network (api.md §GET /health `stub_mode`) |
| LLM API key | `DAA_GEMINI_API_KEY` — REQUIRED when `DAA_LLM_PROVIDER=gemini`; env var NAME only, never the value |
| LLM model | `DAA_LLM_MODEL` — default `gemini-2.5-flash`; kept in config, never hardcoded |
| Max upload size | 200 MB per file; content-types: `text/csv`, `application/json`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/octet-stream` (Parquet) |
| Single-tenant | yes — no auth, one local user |
| Runtime budget | p95 query latency ≤ 10 s (end-to-end including LLM); per-query hard timeout 30 s; max rendered rows 10 000 |
| Concurrency / volume envelope | 1 concurrent session per server instance (single-tenant local); max result rows 100 000 × 64 cols; max upload count per session 20 files |

<!-- The live /health response shape and the stub_mode flag are defined once in spec/api.md §GET /health. -->
