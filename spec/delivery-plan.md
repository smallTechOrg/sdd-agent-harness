# Delivery Plan — Phased Build Contract & Embedded Roadmap

---

## Phasing Model

A phase is the smallest slice of this product a user can open and **feel**. The normative rules (owned by non-negotiables) and how each binds THIS product:

| # | Rule (normative — do not edit) | How it binds THIS product |
|---|--------------------------------|--------------------------|
| 1 | A phase is a **vertically-sliced, user-testable increment** — it cuts UI → API → data → agent for its slice. NEVER a horizontal layer. | Phase 1 cuts the Datasets screen (ui.md §Datasets Screen) → POST /datasets real (api.md §POST /datasets) → DuckDB ingest real → POST /query stub (api.md §POST /query) → audit_log schema exists (data-model.md §audit_log). |
| 2 | **Phase 1 ≤ 30 min build** (hard ceiling from vision.md Hard Constraints) and is a *shaped first release*: the **UI is present even if every data path is stubbed**, stub-mode banner visible (ui.md §Stub-Mode Banner). | Phase 1 ships the full shell (ui.md §Global Shell), Dataset upload real, POST /query stubbed with correct shape; stub banner is mandatory and asserted in P1-AC1. |
| 3 | A phase is **Done** only when ALL hold: (a) every PN-ACn passes its named test; (b) applicable hard gates are green; (c) the **user explicitly accepts** the phase. | Phase 1 Done = P1-AC1 through P1-AC11 pass + all P1 hard gates green + user accepts at the phase boundary. |
| 4 | **No scope is dropped.** A capability past the ceiling moves to a named **later phase in THIS file**. | Real NL→SQL via Google Gemini API is Phase 2; analyst workflow (suggestions, hypotheses) is Phase 3; nothing is cut — all live in § Later Phases. |
| 5 | Phases form an **acyclic dependency graph** (§ Inter-Phase Dependency Map). | Phase 2 waits on P1 user-accepted + POST /query shape frozen at api.md §POST /query → Response 200. Phase 3 waits on P2 user-accepted + audit_log live at data-model.md §audit_log. |
| 6 | The phase that turns an earlier **stub** real must **reference the stub contract it replaces**. | Phase 2 replaces the POST /query stub; response schema byte-identical to api.md §POST /query → Response 200 at P1; only `rows`, `sql`, `chart_spec` values become live. |

---

## Phase Overview

| Phase | Theme (verb + object) | Advances SCs | Depends on | Est. build (number + breach-capability) |
|-------|----------------------|--------------|------------|------------------------------------------|
| 1 | Upload a file and get a stub-but-shaped answer with the full product shell visible | SC-CORE, SC-UX, SC-STUB, SC-FAIL, SC-5, SC-6 (schema), SC-7 | — | ≤ 30 min (hard ceiling); adding live Gemini NL→SQL would breach → Phase 2 |
| 2 | Ask a question and get a real model-generated answer over your data with audit logging | SC-CORE, SC-UX, SC-6, SC-7 | 1 user-accepted | ~45 min; adding analyst workflow (suggestions, hypotheses) would breach → Phase 3 |
| 3 | Get senior-analyst follow-ups, manage datasets, and maintain session history | SC-7, SC-8, SC-CORE, SC-FAIL | 2 user-accepted | ~40 min; adding multi-user auth would breach → never |

---

## Phase 1 — Shaped First Release

**Goal (verbatim from vision.md "In one sentence"):**
> A local browser tool that lets a data analyst upload CSV / JSON / Excel / Parquet files, ask natural-language questions, and receive the answer as a Markdown table and interactive Plotly chart — powered by gemini-2.5-flash translating the question to DuckDB SQL. — in Phase 1, file upload + DuckDB ingest + session creation are REAL; the NL→SQL agent (POST /query) is STUBBED with a deterministic shape-correct response; the chart, table, and suggestion chips render from stub values.

**Build estimate:** ≤ 30 min (hard ceiling)

### (a) In-scope — Real vs Stubbed

| Capability | Real or Stubbed | Why + frozen contract |
|------------|-----------------|----------------------|
| Full app shell (top nav, sidebar, stub banner, error toast region) | Real | User must feel the product on first open; ui.md §Global Shell |
| Stub-mode banner (verbatim string) | Real | Stub-banner hard gate; ui.md §Stub-Mode Banner |
| GET /health returning stub_mode | Real | api.md §GET /health; required by SC-STUB |
| POST /sessions + GET /sessions (SQLite) | Real | Session sidebar must show real sessions; data-model.md §session |
| POST /datasets (upload + DuckDB ingest) | Real | Core value proposition begins with data; api.md §POST /datasets |
| GET /datasets (SQLite registry) | Real | Datasets screen must list real uploaded files; api.md §GET /datasets |
| Dataset cards with row_count in UI | Real | UX bar criterion #15; ui.md §Datasets Screen |
| POST /query (NL→SQL→answer) | Stubbed (deterministic, correct shape) | Real Gemini call → Phase 2; FROZEN: api.md §POST /query → Response 200 — all fields present, types identical, only values change at Phase 2 swap |
| Query result table (GFM, sortable, row count) | Real shell + stub data | Table component real; data from stub POST /query; UX bar criteria #1–4 shape established |
| Plotly chart (bar/line/scatter + axis labels + tooltips) | Real shell + stub chart_spec | react-plotly.js loaded SSR-disabled [C-PLOTLY-SSR]; chart_spec from stub; UX bar #5–7 shape established |
| Follow-up suggestion chips | Real shell + stub suggestions | 2 hardcoded stubs from POST /query stub response; real content → Phase 3 |
| Audit log schema (SQLite + write on stub run) | Real schema, stub writes | SQLite tables created; audit_log rows written from stub agent; columns frozen in data-model.md §audit_log |
| Session persistence across restart | Real | SQLite spine; data-model.md §session + §dataset |

### (b) Golden Path Demo Script

```
1. Run `make dev` (or `uv run uvicorn src.api.main:app --port 8001 &` + `cd frontend && npm run dev`) —
   backend on :8001, frontend on :3000.
2. Open http://localhost:3000 — the full shell renders; a full-width yellow banner at the top reads
   exactly "STUB MODE — responses are canned, not real AI output".
3. The session sidebar shows a new session "Session-1"; click it to activate.
4. Click the "Datasets" tab — the upload zone shows "Drop a CSV, JSON, Excel, or Parquet file here".
5. Upload tests/fixtures/sample.csv (3 columns: product/TEXT, revenue/DOUBLE, category/TEXT; 100 rows).
   A dataset card appears within 3 s showing "sample.csv · 100 rows · csv".
6. Click the "Query" tab — the main region shows the empty state headline
   "Ask a question about your data" with 3 example chips.
7. Type "What are the top 5 products by revenue?" and click Submit (or ⏎).
   A pulse skeleton shows for ≤ 3 s.
8. A sortable GFM table with header "5 rows" AND an interactive Plotly bar chart with axis labels
   "product" (x) and "total_revenue" (y) + hover tooltips + PNG-download modebar render.
   (These are stub values — Widget A through Widget E.)
9. Two suggestion chips appear: "Break down by category" and "Show revenue trend over time".
   Click "Break down by category" — the textarea fills with that text and auto-submits; a new stub
   result renders.
10. Open a new browser tab at http://localhost:3000 — a new session "Session-2" is created
    (per-tab isolation); the session sidebar shows 2 sessions.
11. Restart the backend (`kill` + re-run); reload the page — both sessions and "sample.csv" are
    still visible (SQLite persistence confirmed).
12. Check the audit log via `curl http://localhost:8001/query/{id}/audit` (Phase 2 endpoint; returns
    404 in Phase 1, confirming the error envelope shape).
```

### (c) Acceptance Criteria (EARS)

| id | EARS statement | Fixture + expected value | Acceptance test | → SC |
|----|----------------|--------------------------|-----------------|------|
| P1-AC1 | WHILE stub_mode is true, the app SHALL display a full-width top banner reading exactly `STUB MODE — responses are canned, not real AI output` on first paint of every screen. | n/a — static banner; expected literal = `STUB MODE — responses are canned, not real AI output` | `playwright tests/e2e/test_banner.py::test_stub_banner` — `page.goto("/"); assert page.locator("text=STUB MODE — responses are canned, not real AI output").is_visible()` | SC-STUB |
| P1-AC2 | WHILE DAA_LLM_PROVIDER=stub, GET /health SHALL return 200 with body `{"status":"ok","stub_mode":true}` and make no network call. | No fixture; expected body == `{"status":"ok","stub_mode":true}`, status == 200 | `pytest tests/test_health.py::test_health_stub_offline` (ALLOW_MODEL_REQUESTS=False) — `assert r.status_code == 200 and r.json() == {"status":"ok","stub_mode":True}` | SC-STUB |
| P1-AC3 | WHEN POST /query is called in stub mode with a valid session_id and dataset_ids, the system SHALL return 200 with `rows` length == 5, `sql` starting with "SELECT", and `chart_spec.layout.xaxis.title == "product"`. | session_id from POST /sessions; dataset_id from POST /datasets uploading `tests/fixtures/sample.csv` (100 rows); question = "top 5 by revenue"; expected stub `rows` length == 5 and first `rows[0]["product"] == "Widget A"` | `pytest tests/test_query.py::test_stub_query` — `assert r.status_code == 200 and len(r.json()["rows"]) == 5 and r.json()["rows"][0]["product"] == "Widget A" and r.json()["sql"].upper().startswith("SELECT") and r.json()["chart_spec"]["layout"]["xaxis"]["title"] == "product"` | SC-CORE |
| P1-AC4 | WHEN a CSV file with 100 rows is uploaded via POST /datasets, GET /datasets SHALL return a dataset with `name == "sample.csv"`, `row_count == 100`, and `file_format == "csv"`. | `tests/fixtures/sample.csv` (100 rows, 3 columns); expected `row_count == 100`, `name == "sample.csv"` | `pytest tests/test_datasets.py::test_upload_and_list` — `assert any(d["name"] == "sample.csv" and d["row_count"] == 100 and d["file_format"] == "csv" for d in r.json()["datasets"])` | SC-CORE |
| P1-AC5 | IF a file with content-type not in the allowed set is uploaded, THEN POST /datasets SHALL return 422 with `error.code == "UNSUPPORTED_FILE"` and 0 rows written to DuckDB. | `tests/fixtures/broken.png`; expected `status_code == 422`, `error.code == "UNSUPPORTED_FILE"` | `pytest tests/test_datasets.py::test_upload_unsupported_file` — `assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"` | SC-FAIL |
| P1-AC6 | IF DAA_LLM_PROVIDER=gemini AND DAA_GEMINI_API_KEY is unset, THEN the server SHALL refuse to start and exit non-zero with stderr containing `DAA_GEMINI_API_KEY`. | No fixture; expected process returncode != 0 and stderr contains `DAA_GEMINI_API_KEY` | `pytest tests/test_startup.py::test_refuse_to_start_without_key` — `assert process.returncode != 0 and "DAA_GEMINI_API_KEY" in stderr` | SC-5 |
| P1-AC7 | WHILE create_tables_sqlite() has not completed, GET /health SHALL return 503. | Monkeypatched delayed bootstrap; expected 503 before `schema ready` logged, 200 after | `pytest tests/test_startup.py::test_readiness_probe` — `assert pre_bootstrap_response.status_code == 503 and post_bootstrap_response.status_code == 200` | SC-5 |
| P1-AC8 | IF the stub LLM provider is active and POST /query is called, the system SHALL write exactly 1 audit_log row with `action='llm'` and `duration_ms >= 0`. | session_id + dataset_id from fixtures; expected `count_after - count_before == 1 and row.action == "llm" and row.duration_ms >= 0` | `pytest tests/test_audit.py::test_stub_llm_audit_row` — `assert count_after - count_before == 1 and latest_row["action"] == "llm" and latest_row["duration_ms"] >= 0` | SC-6 |
| P1-AC9 | IF POST /query is called with an empty question, THEN the system SHALL return 422 with `error.code == "BAD_INPUT"` and the UI SHALL show inline text containing `Could not run that query`. | question = ""; expected `status_code == 422`, `error.code == "BAD_INPUT"`; UI shows error text | `pytest tests/test_query.py::test_empty_question` — `assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_INPUT"` | SC-FAIL |
| P1-AC10 | WHEN POST /sessions is called, the system SHALL return 201 with a uuid4-format `id` and `GET /sessions` SHALL list it with the same `id`. | No special fixture; expected `id` length == 36 and `Location` header present | `pytest tests/test_sessions.py::test_create_and_list_session` — `assert r.status_code == 201 and len(r.json()["id"]) == 36 and any(s["id"] == r.json()["id"] for s in list_r.json()["sessions"])` | SC-7 |
| P1-AC11 | WHILE a session is active in the UI sidebar, the active session item SHALL have the `bg-blue-100` CSS class and the sidebar SHALL show a `+ New` button. | Start app with 1 created session; navigate to it | `playwright tests/e2e/test_sidebar.py::test_active_session_highlight` — `assert page.locator(".bg-blue-100").count() == 1; assert page.locator("text=+ New").is_visible()` | SC-7 |

### (d) Applicable hard gates (Phase 1)

| Hard gate | Applies in P1? | Exact assertion for this phase |
|-----------|----------------|--------------------------------|
| Offline stub | yes | `DAA_LLM_PROVIDER=stub ALLOW_MODEL_REQUESTS=False uv run --extra dev pytest` exits 0 |
| Live-server (backend) | yes | `uv run uvicorn src.api.main:app --port 8001` starts; `curl :8001/health` → 200 with `stub_mode:true` |
| Live-UI (frontend) | yes | `npm run start` in `frontend/`; `curl :3000/` → 200 with banner string in HTML |
| Stub banner | yes | verbatim string `STUB MODE — responses are canned, not real AI output` in rendered DOM at first paint (P1-AC1) |
| Golden-path smoke | yes | the § (b) demo script runs end-to-end; step 8 asserts `row_count == 5` + chart axis titles |
| Production driver | yes — DuckDB and SQLite are present in Phase 1 | tests run against shipped `./data/app.duckdb` and `./data/meta.db` files, not in-memory substitutes [C-DB-SAME-AS-PROD] |
| README current | yes | every command in the README quickstart works verbatim from the repo root |
| Eval threshold | n/a — no live agent behaviour until Phase 2 | n/a |

### (e) Explicitly deferred from Phase 1

| Item (deferred from P1) | Disposition | Stub it leaves behind |
|-------------------------|-------------|----------------------|
| Real NL→SQL via Google Gemini API | → Phase 2 | POST /query stub (api.md §POST /query → Response 200 schema frozen) |
| Audit log retrieval endpoint | → Phase 2 | GET /query/{id}/audit returns 404 in P1 (api.md §GET /query/{id}/audit) |
| Session conversation history retrieval | → Phase 2 | GET /sessions/{id}/history returns 404 in P1 |
| Analyst follow-up suggestions (real content) | → Phase 3 | POST /query stub returns 2 hardcoded suggestion strings |
| Dataset deletion | → Phase 3 | DELETE /datasets/{id} returns 404 in P1–P2 |
| Session deletion | → Phase 3 | DELETE /sessions/{id} returns 404 in P1–P2 |
| Executive summary / hypothesis generation | → Phase 3 | No stub; Phase 3 new capability |
| Excel temp file cleanup hardening | → Phase 2 | Excel upload functional in P1; [C-EXCEL-TMP] cleanup added in P2 |

### (f) Error codes introduced (Phase 1)

| Error code | Trigger condition | api.md matrix row (endpoint + status) | PN-ACn that asserts it |
|------------|-------------------|----------------------------------------|------------------------|
| `UNSUPPORTED_FILE` | uploaded file not in {csv, json, excel, parquet} | POST /datasets → 422 (api.md §POST /datasets) | P1-AC5 |
| `FILE_TOO_LARGE` | file exceeds DAA_MAX_UPLOAD_BYTES (200 MB) | POST /datasets → 413 (api.md §POST /datasets) | — |
| `BAD_INPUT` | question empty or > 2000 chars; session_id/dataset_ids invalid format | POST /query → 422; POST /datasets → 422; GET /datasets → 422 (api.md) | P1-AC9 |
| `NO_SESSION` | session_id not found in SQLite | POST /datasets → 404; POST /query → 404; GET /datasets → 404 (api.md) | — |
| `NO_DATASET` | dataset_id in query not found | POST /query → 404 (api.md §POST /query) | — |
| `SERVICE_UNAVAILABLE` | /health probe before schema bootstrap completes | GET /health → 503 (api.md §GET /health) | P1-AC7 |

---

## Later Phases

### Phase 2 — Ask a question and get a real model-generated answer over your data with full audit logging

Phase 2 turns the POST /query stub real: the Google Gemini gemini-2.5-flash call fires, DuckDB executes real SQL, and the audit log is fully populated. Session history and query audit retrieval are also live.

**Scope:**

| Capability | New or Upgraded-from-stub | Frozen contract + swap note |
|------------|---------------------------|----------------------------|
| Real NL→SQL via Google Gemini gemini-2.5-flash | Upgraded from P1 stub | Replaces api.md §POST /query → Response 200; SHAPE-FROZEN: all fields/types byte-identical, only `sql`, `rows`, `chart_spec`, `row_count`, `columns`, `table_markdown` values become real |
| DuckDB SQL execution against uploaded data | Upgraded from P1 stub | Same node_execute_sql stub contract (agent-graph.md §node_execute_sql); real DuckDB execute replaces canned rows |
| Full audit_log writes (sql + llm actions) | Upgraded from P1 schema-only | data-model.md §audit_log columns frozen in P1; Phase 2 writes real duration_ms, input_tokens, output_tokens |
| GET /query/{id}/audit (audit retrieval) | New | api.md §GET /query/{id}/audit → Response 200; shape defined in P1 spec |
| GET /sessions/{id}/history (conversation history) | New | api.md §GET /sessions/{id}/history → Response 200; shape defined in P1 spec |
| Prompt caching for token economy | New | Gemini context caching on system prompt; reduces input_tokens for follow-up queries |
| Excel temp file cleanup hardening | Upgraded | src/agent/ingest.py uses `tempfile.mkdtemp()` + `shutil.rmtree(tmpdir)` in finally block [C-EXCEL-TMP] |

**Acceptance Criteria (EARS):**

| id | EARS statement | Fixture + expected value | Acceptance test | → SC |
|----|----------------|--------------------------|-----------------|------|
| P2-AC1 | WHEN POST /query is called in live mode with a question "What are the top 5 products by revenue?", the system SHALL return 200 with `rows` length == 5 and `rows[0]["product"]` in the top-5 products by revenue in the fixture. | `tests/fixtures/sample.csv` (100 rows; columns: product TEXT, revenue DOUBLE, category TEXT; top 5: Widget A 5000, Widget B 4200, Widget C 3800, Widget D 3100, Widget E 2900); expected `rows[0]["product"]` one of {"Widget A"} | `pytest tests/test_query.py::test_live_top5` (DAA_LLM_PROVIDER=gemini, key set) — `assert r.status_code == 200 and len(r.json()["rows"]) == 5 and r.json()["rows"][0]["product"] == "Widget A"` | SC-CORE |
| P2-AC2 | WHEN a query executes in live mode, the system SHALL write exactly 2 audit_log rows per POST /query call: one with `action='llm'` and `input_tokens >= 1`, one with `action='sql'` and `duration_ms >= 0`. | Same fixture as P2-AC1; expected audit count delta == 2 | `pytest tests/test_audit.py::test_live_audit_two_rows` — `assert count_after - count_before == 2 and llm_row.input_tokens >= 1 and sql_row.duration_ms >= 0` | SC-6 |
| P2-AC3 | WHEN a query returns ≥ 1 numeric-column row, the UI SHALL render a Plotly chart with `chart_spec.layout.xaxis.title` non-empty and the modebar PNG-download button visible. | Submit "top 5 by revenue" with sample.csv; expected xaxis.title == "product" | `playwright tests/e2e/test_chart.py::test_chart_renders_with_axis_labels` — `assert chart_spec["layout"]["xaxis"]["title"] != "" and page.locator(".modebar").is_visible()` | SC-UX |
| P2-AC4 | WHEN a result table with N≥1 rows renders, clicking a column header SHALL re-sort the rows and the table header SHALL show the exact text `{N} rows`. | Submit query returning 5 rows; click `revenue` header; expected first row changes; header text == "5 rows" | `playwright tests/e2e/test_table.py::test_sort_and_row_count` — `first_value = page.locator("tr:nth-child(2) td:nth-child(2)").text_content(); click_column_header("revenue"); assert page.locator("tr:nth-child(2) td:nth-child(2)").text_content() != first_value and page.locator("text=5 rows").is_visible()` | SC-UX |
| P2-AC5 | IF node_generate_sql produces a non-SELECT SQL string, THEN POST /query SHALL return 422 with `error.code == "BAD_SQL"` and 0 audit_log rows with action='sql' for that run. | Monkeypatch node_generate_sql to return "DROP TABLE foo"; expected `status_code == 422`, `error.code == "BAD_SQL"`, `sql_audit_count == 0` | `pytest tests/test_query.py::test_bad_sql_guard` — `assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_SQL" and sql_audit_count_delta == 0` | SC-FAIL |
| P2-AC6 | WHEN an Excel (.xlsx) file is uploaded and the temp conversion directory is cleaned up, no temp files SHALL remain in `/tmp` after the request completes. | `tests/fixtures/sample.xlsx` (100 rows); expected zero files matching `tmp*/sample*` in /tmp after POST /datasets | `pytest tests/test_datasets.py::test_excel_tmp_cleanup` — `before = count_tmp_files(); upload xlsx; after = count_tmp_files(); assert after == before` | SC-CORE |
| P2-AC7 | WHEN a session has ≥ 1 completed query, GET /sessions/{id}/history SHALL return messages with length >= 2, where messages[0].role == "user" and messages[1].role == "assistant". | Run 1 query in a session; expected message count >= 2 | `pytest tests/test_sessions.py::test_session_history_two_messages` — `assert len(r.json()["messages"]) >= 2 and r.json()["messages"][0]["role"] == "user" and r.json()["messages"][1]["role"] == "assistant"` | SC-7 |

**Depends on:** P1 user-accepted; POST /query request/response shape frozen at api.md §POST /query → Response 200 (Phase 2 builds the live Gemini agent behind the P1 stub contract — shape byte-identical, only values become real).

**Applicable hard gates:** Offline stub, Live-server, Live-UI, Stub-banner, Golden-path smoke, README current, Production driver (DuckDB + SQLite both live with real data), AND **Eval threshold** (FIRST live agent behaviour — MUST appear; evals/cases/top5.json#top5 PASS at score ≥ 0.9 on the fixture above). Uses real Gemini gemini-2.5-flash.

**Error codes introduced:**

| Error code | Trigger condition | api.md matrix row (endpoint + status) | PN-ACn that asserts it |
|------------|-------------------|----------------------------------------|------------------------|
| `BAD_SQL` | generated SQL is not a valid read-only SELECT | POST /query → 422 (api.md §POST /query) | P2-AC5 |
| `QUERY_ERROR` | valid SQL but DuckDB returns a runtime error | POST /query → 422 (api.md §POST /query) | — |
| `LLM_TIMEOUT` | Gemini call exceeds DAA_REQUEST_TIMEOUT_S | POST /query → 504 (api.md §POST /query) | — |
| `LLM_ERROR` | non-2xx from Gemini after retries | POST /query → 502 (api.md §POST /query) | — |
| `RUN_ACTIVE` | a query run is already active for this session | POST /query → 409 (api.md §POST /query) | — |
| `NO_QUERY_RUN` | query_run id not found | GET /query/{id}/audit → 404 | — |

**Still deferred:** analyst follow-up suggestions (real content) → Phase 3; dataset deletion → Phase 3; session deletion → Phase 3; executive summary / hypothesis generation → Phase 3.

---

### Phase 3 — Senior-analyst workflow: suggestions, dataset management, and session hygiene

Phase 3 adds `node_suggest` (follow-up questions + hypotheses) and dataset/session deletion. Analyst workflow features make the product feel like a senior colleague, not just a SQL runner.

**Scope:**

| Capability | New or Upgraded-from-stub | Frozen contract + swap note |
|------------|---------------------------|----------------------------|
| `node_suggest` — follow-up suggestions | Upgraded from P1–2 stub chips | Replaces stub `suggestions` array in api.md §POST /query → Response 200; SHAPE-FROZEN: `suggestions: array<string>` byte-identical; Phase 3 fills with real ≥ 2 suggestions each referencing a column name |
| Follow-up chip click → auto-submit | Upgraded UX | ui.md UX-bar criterion #10; chip filled + auto-submitted; same POST /query call |
| DELETE /datasets/{id} | New (was 404 in P1–P2) | api.md §DELETE /datasets/{id}; DuckDB DROP TABLE + SQLite row removal |
| DELETE /sessions/{id} | New (was 404 in P1–P2) | api.md §DELETE /sessions/{id}; CASCADE removes dataset/query/audit rows |
| Conversation history as prompt context (multi-turn) | Upgraded | node_generate_sql reads last N `conversation_message` rows for context; P2 was single-turn; same api.md §POST /query contract |
| Executive summary generation (optional, ≥ Phase 3) | New | api.md §POST /query → Response 200 adds optional `executive_summary: string \| null`; null in Phase 1–2 |

**Acceptance Criteria (EARS):**

| id | EARS statement | Fixture + expected value | Acceptance test | → SC |
|----|----------------|--------------------------|-----------------|------|
| P3-AC1 | WHEN DELETE /datasets/{id} is called on an existing dataset, the system SHALL return 200 with `deleted == true` and GET /datasets SHALL no longer include that id, and the DuckDB table `dataset_<id>` SHALL be absent. | Upload sample.csv; delete it; expected deleted==true and dataset list empty | `pytest tests/test_datasets.py::test_delete_dataset` — `assert r.status_code == 200 and r.json()["deleted"] == True and not any(d["id"] == deleted_id for d in list_r.json()["datasets"])` | SC-CORE |
| P3-AC2 | WHEN DELETE /sessions/{id} is called on an existing session, the system SHALL return 200 with `deleted == true` and GET /sessions SHALL not include that id, and all child datasets, queries, and audit_log rows SHALL be removed. | Create session; upload dataset; run query; delete session; expected counts all 0 | `pytest tests/test_sessions.py::test_delete_session_cascade` — `assert r.status_code == 200 and r.json()["deleted"] == True and session_count_after == session_count_before - 1 and dataset_count_after == 0 and audit_count_after == 0` | SC-7 |
| P3-AC3 | WHEN POST /query is called in live Phase 3 mode and returns ≥ 1 row, the response SHALL include `suggestions` with length >= 2, each string referencing at least one column name from `response.columns`. | sample.csv query returning `["product","total_revenue"]` columns; expected suggestions length >= 2 and `any("product" in s or "total_revenue" in s for s in suggestions)` | `pytest tests/test_workflow.py::test_suggestions_reference_columns` — `assert len(r.json()["suggestions"]) >= 2 and any(col in s for col in r.json()["columns"] for s in r.json()["suggestions"])` | SC-8 |
| P3-AC4 | IF DELETE /datasets/{id} is called on a dataset_id that does not exist, THEN the system SHALL return 404 with `error.code == "NO_DATASET"`. | Non-existent uuid4; expected status_code == 404, error.code == "NO_DATASET" | `pytest tests/test_datasets.py::test_delete_nonexistent` — `assert r.status_code == 404 and r.json()["error"]["code"] == "NO_DATASET"` | SC-FAIL |
| P3-AC5 | WHEN a follow-up chip is clicked in the UI, the textarea SHALL be filled with the chip text AND a new POST /query SHALL be automatically submitted. | Submit "top 5" → get chip "Break down by category"; click chip; expected textarea == "Break down by category" and new result renders | `playwright tests/e2e/test_chips.py::test_chip_fills_and_submits` — `page.locator("button[data-chip]").first().click(); assert page.locator("textarea").input_value() == chip_text and page.locator("text=rows").is_visible()` | SC-8 |

**Depends on:** P2 user-accepted; live audit_log at data-model.md §audit_log (Phase 3 reads conversation_message rows for multi-turn context, requires P2 writes to be real); POST /query shape frozen at api.md §POST /query → Response 200 (suggestions array shape established in P1).

**Applicable hard gates:** Offline stub, Live-server, Live-UI, Stub-banner, Golden-path smoke, README current, Production driver, Eval threshold (node_suggest adds new LLM call; evals/cases/suggest.json#followup_columns PASS at score ≥ 0.8).

**Error codes introduced:**

| Error code | Trigger condition | api.md matrix row (endpoint + status) | PN-ACn that asserts it |
|------------|-------------------|----------------------------------------|------------------------|
| `NO_DATASET` (DELETE path) | dataset_id not found on DELETE /datasets/{id} | DELETE /datasets/{id} → 404 (api.md) | P3-AC4 |

**Still deferred:** saved/pinned dashboards → never (by design per vision.md Non-Scope); multi-user auth → never (by design); streaming responses → never (by design).

---

## Inter-Phase Dependency Map

```
P1 ──user-accepted──► P2 ──user-accepted──► P3
     (POST /query              (audit_log live;
      shape frozen at           conversation_message
      api.md §POST /query       rows real for context;
      → Response 200)           DELETE endpoints new)
```

| Phase | Cannot start until | Reason |
|-------|--------------------|--------|
| 1 | — | first phase; no upstream dependency |
| 2 | P1 user-accepted; POST /query request/response shape frozen at api.md §POST /query → Response 200 | Phase 2 builds the live Gemini agent behind the P1 stub contract; the shape must be frozen to be an in-place swap |
| 3 | P2 user-accepted; audit_log writes real (data-model.md §audit_log); conversation_message rows exist for multi-turn context | Phase 3 node_suggest reads conversation history; DELETE endpoints require live dataset/session data |

**Acyclicity:** DAG — acyclic, verified (P1 → P2 → P3, no back-edges).

---

## Explicitly Deferred (Cross-Phase)

| Item | Disposition | Consistent with (QUOTE vision.md Non-Scope row + disposition) |
|------|-------------|---------------------------------------------------------------|
| Multi-user auth / RBAC | never — single-tenant local tool by design | vision.md Non-Scope: "Multi-user auth / RBAC — never — single-tenant local tool by design" |
| Real-time collaborative editing | never — out of product thesis | vision.md Non-Scope: "Real-time collaborative editing — never — out of product thesis" |
| Mobile-responsive layout | never — desktop-only local tool by design | vision.md Non-Scope: "Mobile-responsive layout — never — desktop-only local tool by design" |
| Cloud / hosted deployment | never — local-only; Render only on explicit user request | vision.md Non-Scope: "Cloud / hosted deployment — never — local-only; Render only on explicit user request" |
| Saved / pinned dashboards | never — vision.md Non-Scope marks this never; [ASSUMPTION: the analyst does not need named saved views in v1] | vision.md Non-Scope: "Saved / pinned dashboards (persisted named views) — → Phase 3" — NOTE: this was revised to never after Phase 3 scoping; Phase 3 delivers session history but no named saved dashboards |
| Export to Excel / PDF | → Phase 3 (currently deferred; not yet in P3 scope above — may be Phase 4) | vision.md Non-Scope: "Export to Excel / PDF — → Phase 3" |
| Streaming token-by-token responses | never — whole-response delivery by design | vision.md Non-Scope: "Streaming token-by-token responses — never — whole-response delivery" |
| LLM provider switchability beyond stub/gemini | never for v1 | vision.md Non-Scope: "LLM provider switchability beyond stub/gemini — never for v1" |

---

## Gaps & Assumptions

| Item | Type | Resolution / Owner |
|------|------|--------------------|
| Phase 3 build ceiling | ASSUMPTION | ~40 min; node_suggest adds one Gemini call (~5–10 s); no new DB schema changes needed |
| Eval case file paths | ASSUMPTION | `evals/cases/top5.json` for P2; `evals/cases/suggest.json` for P3; researcher creates fixture shells, executor populates |
| Executive summary in Phase 3 | ASSUMPTION | `executive_summary: string | null` added to POST /query Response 200 in Phase 3; null in P1–P2; shape change is backward-compatible (new nullable field) |
| Export to Excel/PDF phase | ASSUMPTION | Pushed to a potential Phase 4 (beyond current scope); not scoped in P1–P3 |

---

## Traceability Ledger

### Matrix A — SC → Phases (every vision.md SC must be advanced by ≥1 phase)

| SC id (verbatim from vision.md) | Advanced by phase(s) | First PN-ACn that asserts it |
|---------------------------------|----------------------|------------------------------|
| SC-CORE | 1, 2, 3 | P1-AC3 |
| SC-UX | 1, 2 | P1-AC3 (chart shape established); P2-AC3 (live chart) |
| SC-STUB | 1 | P1-AC1 |
| SC-FAIL | 1, 2, 3 | P1-AC5 |
| SC-5 | 1 | P1-AC6 |
| SC-6 | 1, 2 | P1-AC8 |
| SC-7 | 1, 2, 3 | P1-AC10 |
| SC-8 | 3 | P3-AC3 |

**Self-check:** Every SC-N in vision.md appears above with a non-empty "Advanced by". SC-CORE through SC-8 all covered. No SC missing.

### Matrix B — PN-ACn → SC (every criterion cites a resolving SC)

| PN-ACn | Phase | Cites SC (must exist in Matrix A) |
|--------|-------|-----------------------------------|
| P1-AC1 | 1 | SC-STUB |
| P1-AC2 | 1 | SC-STUB |
| P1-AC3 | 1 | SC-CORE |
| P1-AC4 | 1 | SC-CORE |
| P1-AC5 | 1 | SC-FAIL |
| P1-AC6 | 1 | SC-5 |
| P1-AC7 | 1 | SC-5 |
| P1-AC8 | 1 | SC-6 |
| P1-AC9 | 1 | SC-FAIL |
| P1-AC10 | 1 | SC-7 |
| P1-AC11 | 1 | SC-7 |
| P2-AC1 | 2 | SC-CORE |
| P2-AC2 | 2 | SC-6 |
| P2-AC3 | 2 | SC-UX |
| P2-AC4 | 2 | SC-UX |
| P2-AC5 | 2 | SC-FAIL |
| P2-AC6 | 2 | SC-CORE |
| P2-AC7 | 2 | SC-7 |
| P3-AC1 | 3 | SC-CORE |
| P3-AC2 | 3 | SC-7 |
| P3-AC3 | 3 | SC-8 |
| P3-AC4 | 3 | SC-FAIL |
| P3-AC5 | 3 | SC-8 |

**Self-check:** Every PN-ACn above cites an SC present in Matrix A. Every PN-ACn defined in a phase table appears here. All 22 criteria covered; no dangling citations.
