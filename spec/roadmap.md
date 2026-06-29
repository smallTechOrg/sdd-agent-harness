# Roadmap

---

## What This Agent Does

A personal, local-first data-analysis agent for a single power user. The user uploads tabular data (CSV first; Excel later) and asks questions in plain English. The agent answers like a careful analyst: it states the key number(s), and — every time — shows the **exact query that produced each figure** so the answer is auditable. It is production-grade: the user acts on the answers, so the agent computes locally, never silently guesses, flags any best-guess, and persists a full run history as an audit trail.

The defining invariant is a **hard privacy boundary**: a local DuckDB engine does all data crunching; the LLM only ever sees the schema, column names, and aggregate/result rows — **never raw data rows**. No raw row leaves the machine.

## Who Uses It

A single power user (analyst / founder / operator) running the tool locally on their own machine, against their own data. They are comfortable asking analytical questions but want the speed of natural language plus the rigour of seeing the underlying SQL. They do not want their raw data sent to a cloud LLM.

## Core Problem Being Solved

Today the user either writes SQL/spreadsheet formulas by hand (slow, error-prone) or pastes data into a cloud chatbot (privacy risk, unverifiable answers). This agent gives the speed of natural-language Q&A with the trust of a local compute engine and a visible, exact query behind every number — and keeps the data on the machine.

## Success Criteria

- [ ] User uploads a CSV and, within one session, gets a correct plain-English answer to a question with the **exact DuckDB SQL** shown beneath it.
- [ ] The figure in the answer is reproducible: running the shown SQL against the uploaded data yields the same number.
- [ ] No raw data row is ever included in any payload sent to Gemini — only schema and aggregate/result rows (verified by an automated test that inspects the prompt).
- [ ] Every question/answer is persisted (question, generated SQL, result, timestamp) as an audit trail.
- [ ] A 100MB CSV answers a simple aggregate question in under 30 seconds on the core path.
- [ ] When the model produces invalid SQL, the agent retries with the DuckDB error fed back, and either succeeds or returns a clearly-flagged failure — it never returns a fabricated number.

## What This Agent Does NOT Do (Out of Scope)

- No multi-user / multi-tenant access, auth, or cloud deployment — it is single-user and local only.
- No write-back to the user's source files or external systems; it is read-only analysis.
- No sending of raw data rows to any LLM, ever (hard invariant).
- No autonomous scheduled runs — every analysis is user-triggered.
- No fine-tuning or training on the user's data.
- No data sources beyond uploaded files (no live DB connectors, no APIs) in any planned phase.

## Key Constraints

- **Privacy:** hard boundary — LLM sees schema + aggregate/result rows only, never raw rows.
- **Files:** up to ~100MB per dataset.
- **Latency:** core answer path under 30s.
- **Local-only:** runs on `http://localhost:8001/app/`, single process, single user.
- **SQL dialect is DuckDB** — all generated SQL must be DuckDB-valid (see `architecture.md` and `agent.md`).
- **Cost-aware:** Gemini token usage and estimated cost are tracked per query (UI surfaced from Phase 2/3).

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is REAL on the one core path (upload → ask → answer-with-SQL). Its frontend is visually complete: real UI for that path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Later phases wire those stubs into real functionality.

### Phase 1 — Ask & Answer with Exact SQL (core path)

- **Goal:** The user uploads one CSV, asks one plain-English question, and gets a plain-English answer with the key number(s) AND the exact DuckDB SQL that produced it — computed locally in DuckDB, with only schema + aggregate result rows sent to Gemini. Capability: [analyze_question](capabilities/analyze_question.md).
- **Independent slices (parallel build units):**
  - `backend-ingest-analysis` (backend) — DuckDB dependency + ingest of an uploaded CSV into a per-session DuckDB file; the `analyze_question` LangGraph node (generate-SQL → execute-in-DuckDB → answer, with retry-on-SQL-error); the upload + ask endpoints; `Dataset` and `Run` DB models + Alembic migration; the analysis system prompt; observability logging; tests (unit + real-Gemini integration covering the golden path and the privacy-boundary assertion). **Deps: none.**
  - `frontend-core-ui` (frontend) — upload control, dataset summary, question box, answer panel showing answer + exact SQL, plus clearly-LABELLED "Coming soon" stubs for charts, summary tables, multi-dataset, memory, cost UI, audit-trail browsing; Playwright E2E smoke test of the upload→ask→answer journey. **Deps: the ask-endpoint response contract — specified in [api.md](api.md) so both slices build to it without serializing.**
- **Key surfaces / files:**
  - backend: `src/analysis/duckdb_engine.py`, `src/analysis/ingest.py`, `src/graph/nodes.py` (replace `transform_text`), `src/graph/state.py`, `src/graph/agent.py`, `src/graph/edges.py`, `src/prompts/analysis.md`, `src/api/datasets.py`, `src/domain/analysis.py`, `src/db/models.py`, `alembic/versions/0002_datasets_runs.py`, `pyproject.toml` (add `duckdb`), `tests/unit/...`, `tests/integration/test_analysis.py`.
  - frontend: `frontend/src/app/page.tsx`, `frontend/src/components/*`, `frontend/tests/e2e/core_path.spec.ts`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest` (real Gemini key from `.env`; SQLite app DB via the production driver; DuckDB compute engine).
- **How the user tests it (handoff seed):** Run `uv run python -m src`, open `http://localhost:8001/app/`. Upload a CSV (a sample is provided). The dataset summary (row count, columns) appears — REAL. Type a question like "What is the total revenue?" and submit. Within ~30s the answer appears with the key number and, beneath it, the exact DuckDB SQL — REAL. The Charts, Summary Table, Datasets sidebar, Cost meter, and History tabs are visible but greyed-out and labelled "Coming soon" — STUBS, not bugs.

### Phase 2 — Analyst Polish (profiling, charts, tables, follow-ups)

- **Goal:** Each answer becomes a full analyst response: an auto-chosen chart, a summary table, and 2–3 suggested follow-up questions; and every dataset is auto-profiled on upload. Capabilities: [profile_dataset](capabilities/profile_dataset.md), [render_chart](capabilities/render_chart.md), [summarize_result](capabilities/summarize_result.md), [suggest_followups](capabilities/suggest_followups.md).
- **Independent slices (parallel build units):**
  - `backend-profiling` (backend) — `profile_dataset` runs on upload (DuckDB-computed column types, null counts, distinct counts, min/max); profile stored on `Dataset`. **Deps: none.**
  - `backend-answer-enrichment` (backend) — extend the analysis result with a chart spec (chart-type chosen from result shape), a summary-table payload, and follow-up suggestions (Gemini, from schema + result only). New graph nodes after `answer`. **Deps: none (shares response contract via api.md).**
  - `frontend-rich-answer` (frontend) — wire the chart (client-side render of the backend chart spec), summary table, profile panel, and follow-up chips into the previously-stubbed surfaces. **Deps: response shape from `backend-answer-enrichment` + `backend-profiling`, specified in api.md.**
- **Key surfaces / files:** backend `src/analysis/profiler.py`, `src/analysis/charts.py`, `src/graph/nodes.py`, `src/prompts/*.md`, `src/api/datasets.py`, migration `0003_*`; frontend `frontend/src/components/Chart.tsx`, `SummaryTable.tsx`, `ProfilePanel.tsx`, `Followups.tsx`, `frontend/tests/e2e/rich_answer.spec.ts`.
- **Gate command:** `uv run pytest` (real Gemini key from `.env`).
- **How the user tests it (handoff seed):** Re-upload a CSV; a profile panel now shows per-column stats. Ask a question; the answer now includes a chart, a summary table, and clickable follow-up chips (clicking one asks it). Multi-dataset, memory, cost UI, and audit-trail tabs remain labelled "Coming soon".

### Phase 3 — Power Sessions (memory, multi-dataset, notes, cost, audit, streaming, Excel)

- **Goal:** Upload-once-ask-many sessions that persist across days over multiple datasets the user can compare/join; conversation memory; user notes about data; live step streaming; cost meter + expensive-query warning; full audit-trail browsing; Excel ingest. Capabilities: [manage_session_memory](capabilities/manage_session_memory.md), [multi_dataset_query](capabilities/multi_dataset_query.md), [data_notes](capabilities/data_notes.md), [cost_tracking](capabilities/cost_tracking.md), [audit_trail](capabilities/audit_trail.md), [excel_ingest](capabilities/excel_ingest.md).
- **Independent slices (parallel build units):**
  - `backend-sessions-memory` (backend) — `Session` entity, conversation-turn memory fed into the planning prompt, persistence across restarts. **Deps: none.**
  - `backend-multi-dataset` (backend) — multiple datasets loaded in one DuckDB connection; cross-dataset/join queries; `data_notes` (per-dataset user notes fed to the prompt). **Deps: none.**
  - `backend-cost-audit-excel` (backend) — per-query token/cost capture + running totals; expensive-query pre-warning; audit-trail read API; `openpyxl` Excel ingest. **Deps: none.**
  - `frontend-power-ui` (frontend) — datasets sidebar (multi-select), notes editor, cost meter + warning modal, history browser, live step-streaming view (SSE), Excel upload. **Deps: response/stream contracts from the three backend slices, specified in api.md.**
- **Key surfaces / files:** backend `src/db/models.py` (+ `Session`, `DataNote`), `src/analysis/ingest.py` (Excel), `src/api/*`, streaming endpoint, migrations `0004_*`; frontend `frontend/src/components/*`, `frontend/tests/e2e/power_session.spec.ts`.
- **Gate command:** `uv run pytest` (real Gemini key from `.env`).
- **How the user tests it (handoff seed):** Upload two datasets; ask a question that joins/compares them. Add a note ("revenue is in cents") and confirm a later answer respects it. Watch steps stream live as the agent works. See the cost meter increment and a warning before an expensive query. Open History to browse past runs with their SQL. Re-launch the app and confirm the session/datasets persist. Upload an `.xlsx` and query it.
