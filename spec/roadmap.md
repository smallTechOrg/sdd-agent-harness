# Roadmap

## What This Agent Does

A personal data analysis agent that lets a single user upload CSV and Excel files, ask natural-language questions about the data, and receive streaming plain-text answers paired with auto-selected interactive Plotly charts. The agent runs multi-step Python/pandas code in a sandboxed subprocess, inspects the result, and retries up to 5 times before answering — so the user never writes a line of code. Multi-file operations (join on a shared column, compare metrics, stack/union) are first-class. All sessions and query history persist indefinitely in SQLite.

## Who Uses It

One user — the owner of the personal data files. They work with CSV and Excel files daily, need quick answers and visual summaries from the data, and want a conversational interface rather than a coding environment.

## Core Problem Being Solved

The user must currently open data files in Excel or a Jupyter notebook, write or copy pandas code, debug it, and manually pick a chart type — a slow, fragile loop. This agent replaces that loop: upload once, ask in plain English, get a chart-quality answer in seconds.

## Success Criteria

- [ ] A single CSV file can be uploaded and auto-profiled (column names, types, row count, null counts, 3 sample rows) without any user code.
- [ ] A natural-language question returns a streaming plain-text answer with an embedded Plotly chart and the Python code that produced it, all within one browser interaction.
- [ ] The agent retries with a different code approach on execution error, up to 5 steps, before surfacing failure.
- [ ] Per-query token count and estimated cost display correctly after each answer.
- [ ] Multi-file join/compare/stack operations produce correct results when two files share a column name.
- [ ] All query history persists in SQLite and is visible in the session history sidebar.

## What This Agent Does NOT Do (Out of Scope)

- No multi-user authentication or access control — single-user only.
- No cloud storage of uploaded files — files are stored locally on the server.
- No PostgreSQL; SQLite is the only database.
- No scheduled or background jobs — all analysis is triggered by the user.
- No model training or fine-tuning on the user's data.
- No export of results to external destinations (email, Slack, etc.).
- No SQL database query capability (e.g., connecting to Postgres/MySQL as a data source) — Phase 3 defers this explicitly.

## Key Constraints

- Backend package: `data_analysis` (extends `src/data_analysis/` in place; never creates a parallel package).
- Port: 8001 hard-coded; single-origin model (`frontend/` built as Next.js static export, served by FastAPI at `/app/`).
- LLM: Gemini 2.5 Flash via `AGENT_GEMINI_API_KEY`; model ID configurable via `AGENT_LLM_MODEL` (default `gemini-2.5-flash`).
- Database: SQLite only (`AGENT_DATABASE_URL`, default `sqlite+aiosqlite:///./data_analysis.db`).
- Code execution: subprocess only, never `exec()`/`eval()` in the main process; hard timeout of 30 seconds per step.
- Streaming: Server-Sent Events on `POST /api/query/stream`.
- Observability: structlog to stdout; every query logs question, answer, tokens, estimated cost, and timing.

---

## Phases of Development

> Phase 1 is the smallest first-time-right user-testable win. It must work perfectly the first time the user tests it — zero rough edges on the tested path. The frontend is visually complete: real UI for the one working path, plus clearly-labelled non-functional stubs for everything coming later. A stub must never be mistaken for a bug.

---

### Phase 1 — CSV Upload, Profile, NL Query, Streaming Answer + Chart

**Goal:** The user uploads one CSV file, sees an instant auto-profile (columns, types, row count, nulls, sample rows), types a natural-language question, and receives a streaming answer with an embedded interactive Plotly chart and collapsible Python code. Per-query token count and estimated cost display after each answer. Everything else is a clearly-labelled stub.

**Independent slices (parallel build units):**

- `slice-db-schema` (backend) — SQLite schema + Alembic migration for `uploaded_files` and `query_runs` (Phase 1 tables only). Deps: none.
- `slice-upload-profile` (backend) — `POST /api/files/upload` endpoint + auto-profile logic (pandas column introspection). Deps: none.
- `slice-agent-graph` (backend) — LangGraph agent graph: `profile_data`, `plan_steps`, `execute_code`, `inspect_result`, `decide_continue`, `synthesize_answer` nodes; sandboxed subprocess tool; SSE streaming runner wired to `POST /api/query/stream`. Deps: none (uses same SQLite session as slice-db-schema, but file paths are disjoint).
- `slice-observability` (backend) — structlog setup (`src/data_analysis/observability/`), per-query structured log emission from the SSE runner. Deps: none.
- `slice-frontend` (frontend) — Full single-page UI: left sidebar with upload button + file list (real, wired to `POST /api/files/upload` and `GET /api/files`); main panel with chat input + streaming text + embedded Plotly chart + collapsible code accordion (all real on the one tested path); token/cost footer (real). NON-FUNCTIONAL STUBS labelled in the UI: multi-file panel ("Multi-file join — coming in Phase 2"), session history sidebar ("Session history — coming in Phase 2"). Deps: none.
- `slice-e2e-tests` (backend/frontend) — Playwright E2E suite in `tests/e2e/` covering: file upload → profile display → ask question → streaming answer → Plotly chart rendered → cost display. Deps: slice-frontend must be built first (the only declared dependency across all slices in this phase); all other backend slices can run concurrently with this slice building its test scaffolding, then the final smoke run happens after slice-frontend is built.

**Key surfaces / files:**
- `slice-db-schema`: `src/data_analysis/db/models.py`, `src/data_analysis/db/session.py`, `alembic/versions/<phase1_migration>.py`
- `slice-upload-profile`: `src/data_analysis/api/upload.py`, `src/data_analysis/tools/profiler.py`
- `slice-agent-graph`: `src/data_analysis/graph/state.py`, `src/data_analysis/graph/nodes.py`, `src/data_analysis/graph/edges.py`, `src/data_analysis/graph/agent.py`, `src/data_analysis/graph/runner.py`, `src/data_analysis/tools/code_executor.py`, `src/data_analysis/api/query.py`, `src/data_analysis/prompts/analyst.md`
- `slice-observability`: `src/data_analysis/observability/__init__.py`, `src/data_analysis/observability/logging.py`
- `slice-frontend`: `frontend/src/app/page.tsx`, `frontend/src/components/FileList.tsx`, `frontend/src/components/ChatPanel.tsx`, `frontend/src/components/PlotlyChart.tsx`, `frontend/src/components/CodeAccordion.tsx`, `frontend/src/components/CostFooter.tsx`, `frontend/src/components/StubPanel.tsx`
- `slice-e2e-tests`: `tests/e2e/test_phase1.py` (Playwright + pytest-playwright), `tests/phase1/test_upload.py`, `tests/phase1/test_query.py`

**Gate command:**
```
AGENT_GEMINI_API_KEY=<key> uv run pytest tests/phase1/ tests/e2e/ -x -q
```

All tests must pass with a real Gemini key. The Playwright suite runs Chromium headless against the live app (`http://localhost:8001/app/`). `AGENT_GEMINI_API_KEY` must be set in `.env`.

**How the user tests it (handoff seed):**
1. `cd /path/to/repo && uv run alembic upgrade head`
2. `cd frontend && pnpm build && cd ..`
3. `uv run python -m src` (starts on port 8001)
4. Open `http://localhost:8001/app/` in the browser.
5. **REAL path — upload and query:**
   - Click "Upload CSV" in the left sidebar. Pick any CSV file (a file with at least 500 rows to prove sample ≠ full is recommended). The file appears in the sidebar and the profile panel shows column names, types, row count, null counts, and 3 sample rows immediately.
   - Type a question in the chat input, e.g. "What is the average of [column]?" and press Enter.
   - Watch the answer stream in; the collapsible "Code" accordion shows each Python step tried; a Plotly chart renders inline; the footer shows token count and estimated cost.
6. **Labelled stubs (not bugs):**
   - The sidebar header "Multi-file join — coming in Phase 2" is a visual placeholder; clicking it does nothing.
   - The "Session history — coming in Phase 2" pane is a visual placeholder with a grey "Coming soon" label.

---

### Phase 2 — Multi-File Operations + Persistent Sessions + Query History

**Goal:** The user can upload two or more CSV files, perform join/compare/stack operations via natural language (e.g. "join sales and customers on customer_id"), and see the full query history for the current session in the sidebar. Sessions persist across browser restarts.

**Independent slices (parallel build units):**

- `slice-session-db` (backend) — Alembic migration adding `sessions` and `audit_log` tables; session creation/lookup API (`GET /api/sessions`, `POST /api/sessions`). Deps: none.
- `slice-multi-file-backend` (backend) — Multi-file join/compare/stack logic in the agent graph: extend `plan_steps` and `execute_code` nodes to accept multiple `file_ids`; add `GET /api/files` list endpoint. Deps: none.
- `slice-history-frontend` (frontend) — Wire session history sidebar: list past queries from `GET /api/sessions/{session_id}/queries`; click a past query to show its answer + chart. Deps: none.
- `slice-multi-file-frontend` (frontend) — Wire multi-file panel: file checkboxes, join-column selector, operation picker (join / compare / stack). Deps: none.

**Key surfaces / files:**
- `slice-session-db`: `src/data_analysis/db/models.py` (Session, AuditLog entities), `alembic/versions/<phase2_migration>.py`, `src/data_analysis/api/sessions.py`
- `slice-multi-file-backend`: `src/data_analysis/graph/nodes.py` (extended), `src/data_analysis/tools/multi_file.py`, `src/data_analysis/api/files.py`
- `slice-history-frontend`: `frontend/src/components/SessionHistory.tsx`, `frontend/src/app/page.tsx` (sidebar wiring)
- `slice-multi-file-frontend`: `frontend/src/components/MultiFilePanel.tsx`, `frontend/src/app/page.tsx` (panel wiring)

**Gate command:**
```
AGENT_GEMINI_API_KEY=<key> uv run pytest tests/phase2/ tests/e2e/ -x -q
```

**How the user tests it (handoff seed):**
1. `uv run alembic upgrade head` (applies Phase 2 migration).
2. `cd frontend && pnpm build && cd .. && uv run python -m src`
3. Open `http://localhost:8001/app/`.
4. Upload two CSV files that share a column name. Select both in the multi-file panel. Ask "join [file A] and [file B] on [shared column] and show me the top 10 rows." Verify the chart and answer use merged data.
5. Reload the browser. The session history sidebar shows the previous queries. Click one to restore the answer and chart.

---

### Phase 3 — Excel Support + Follow-Up Suggestions + Full Audit Log + Daily Cost Total

**Goal:** Excel files (`.xlsx`) can be uploaded; after each answer the agent suggests 2–3 follow-up questions; the full audit log (question, code executed, answer, timing, tokens) is stored in SQLite and viewable; the UI footer shows a running daily total cost alongside the per-query cost.

**Independent slices (parallel build units):**

- `slice-excel-support` (backend) — Add `openpyxl` dependency; extend `POST /api/files/upload` to accept `.xlsx`; extend profiler to handle multi-sheet Excel files (profile each sheet). Deps: none.
- `slice-followup-suggestions` (backend) — Add `suggest_followups` node to the agent graph; extend SSE stream to emit a `followups` event type with 2–3 suggested questions. Deps: none.
- `slice-audit-log-api` (backend) — `GET /api/audit` endpoint; ensure `audit_log` rows are written from the SSE runner. Deps: Phase 2 `slice-session-db` (already landed; no intra-phase dependency).
- `slice-daily-cost-frontend` (frontend) — Wire daily cost total from `GET /api/cost/daily`; display in the footer next to per-query cost. Deps: none.
- `slice-followup-frontend` (frontend) — Render follow-up suggestion chips below each answer; clicking a chip fires it as the next question. Deps: none.

**Key surfaces / files:**
- `slice-excel-support`: `src/data_analysis/tools/profiler.py`, `src/data_analysis/api/upload.py`, `pyproject.toml`
- `slice-followup-suggestions`: `src/data_analysis/graph/nodes.py`, `src/data_analysis/graph/agent.py`, `src/data_analysis/graph/state.py`
- `slice-audit-log-api`: `src/data_analysis/api/audit.py`, `src/data_analysis/graph/runner.py`
- `slice-daily-cost-frontend`: `frontend/src/components/CostFooter.tsx`
- `slice-followup-frontend`: `frontend/src/components/FollowUpChips.tsx`, `frontend/src/components/ChatPanel.tsx`

**Gate command:**
```
AGENT_GEMINI_API_KEY=<key> uv run pytest tests/phase3/ tests/e2e/ -x -q
```

**How the user tests it (handoff seed):**
1. `uv run alembic upgrade head` then `cd frontend && pnpm build && cd .. && uv run python -m src`.
2. Upload an `.xlsx` file. Verify the profile panel shows sheet names and column metadata.
3. Ask a question. After the answer, verify 2–3 follow-up chips appear. Click one; it fires as the next question.
4. Check the footer: per-query cost and the running daily total both display.
5. Visit `GET /api/audit` and confirm the row contains question, code, answer, timing, and tokens.
