# Roadmap

> Authoritative product + phase plan for the Local Data Analyst agent.

---

## What This Agent Does

A personal, locally-run data-analysis agent. A single power user uploads a CSV (Excel later — see out-of-scope), and the agent auto-profiles it (rows, columns, types, a health summary). The user then asks natural-language questions ("which region grew fastest last quarter?") and gets back a concise, production-grade answer: a plain-English explanation with the key numbers called out, ONE auto-selected chart, and a compact summary table — plus a collapsible "show its work" panel (the plan, the step trace, and the actual DuckDB SQL it ran). All raw data stays on the machine: the agent generates DuckDB SQL that runs **locally**, and only column schemas and small aggregate results are ever sent to the LLM.

## Who Uses It

A single, technical power user (an analyst / operator) running the tool locally and opening it a few times a day to interrogate their own spreadsheet data. They act on the answers, so the agent must show its reasoning and the exact query it ran. They trust their own machine but do **not** want raw rows leaving it.

## Core Problem Being Solved

Today the user either writes ad-hoc SQL / spreadsheet formulas by hand, or pastes data into a cloud LLM (which leaks raw rows and gives un-auditable answers). This agent replaces both: it answers in natural language, runs the analysis locally over a fast columnar engine (DuckDB), never sends raw rows off-machine, and shows the exact query and plan so the answer is auditable and actionable.

## Success Criteria

- [ ] User can upload a CSV up to ~100MB and see an auto-profile (row count, per-column type, null/health summary) in under ~30s.
- [ ] User can ask a natural-language question and receive a plain-English answer with the key numbers called out, ONE auto-picked chart, and a summary table — in under ~30s.
- [ ] The "show its work" panel always shows the plan, the step trace (tried / failed / worked), and the exact DuckDB SQL executed.
- [ ] No raw data row is ever sent to the LLM — verifiable in the logged trace (LLM inputs contain only schema + aggregate results), enforced by a named guard step.
- [ ] A SQL execution error is never a dead end: the agent feeds the error back and regenerates corrected DuckDB SQL, up to a bounded retry limit, and the retry is visible in the trace.
- [ ] Every question run is persisted to the SQLite DB tied to its dataset, storing the plan, SQL, trace, result, and per-question cost.

## What This Agent Does NOT Do (Out of Scope)

- **Never sends raw data rows to the LLM** — only column schemas and aggregate/summary results. (This is a hard boundary, not a phase.)
- No cloud storage, no external integrations, no multi-user / auth — single local user.
- No write-back to source files; analysis is read-only over the uploaded data.
- No arbitrary Python execution — analysis is expressed as DuckDB SQL only (the LLM-generated-code surface is constrained to SQL).
- Phase 1 does **not** do: multi-file JOIN/compare, conversation follow-ups / memory, suggested follow-up questions, column-notes / business-rule memory, a clarifying-question gate, a running daily cost tally, persistent multi-day dataset browsing, or Excel upload. These ship as clearly-labelled non-functional stubs in Phase 1 and are wired up in later phases.

> **Assumed:** Excel (`.xlsx`) upload is **deferred** to Phase 5 and shipped as a clearly-labelled stub in Phase 1 (the upload control accepts `.csv` only; an "Excel — coming soon" note sits beside it). Rationale: CSV-only keeps Phase 1 the smallest first-time-right win; DuckDB reads CSV natively without an extra parsing dependency, whereas robust Excel ingestion adds a parser and type-coercion surface that would widen the tested path.

> **Assumed:** "Per-question cost" in Phase 1 is computed from Gemini token usage returned on each call and shown per-question; the **running daily total** is a labelled stub (shows "—") until Phase 6, because a daily roll-up needs the cost-aggregation query + UI that is not on the core path.

> **Assumed:** Conversation memory (turn history) is **deferred** to Phase 3 and stubbed in Phase 1. Rationale: the primary Phase-1 journey is "upload → profile → ask ONE question → answer". Each Phase-1 question is independent and self-contained, so single-turn answering is fit for purpose for the Phase-1 win; multi-turn follow-ups (where memory becomes mandatory) are their own increment. The Phase-1 UI shows a disabled "follow-up" affordance labelled "coming soon" so the absence reads as a stub, not a bug.

## Key Constraints

- **Latency:** profile and answer each under ~30s on a ~100MB CSV.
- **Privacy:** raw rows never leave the machine; only schema + aggregates to the LLM.
- **Cost:** keep LLM calls cheap and few — at most one plan call + one SQL-generation call (+ bounded retries) + one answer-phrasing call per question.
- **Dialect safety:** all generated SQL is DuckDB dialect; SQLite-isms (e.g. `julianday`) are forbidden in the prompt and recovered from via retry-on-error.
- **Robustness:** handle messy real-world data — missing values, inconsistent types, odd column names.
- **Local-only:** runs on the user's machine; SQLite for app state, DuckDB for analysis, single origin at `http://localhost:8001/app/`.

## Capabilities

See [`capabilities/index.md`](capabilities/index.md). Active for the build:

| Capability | Phase |
|-----------|-------|
| [profile-on-upload](capabilities/profile-on-upload.md) | 1 |
| [ask-question](capabilities/ask-question.md) | 1 |
| [show-its-work](capabilities/show-its-work.md) | 1 |

Deferred (later phases): conversation-memory (3), multi-file-join (4), suggested-followups (later), clarifying-question gate (later), daily-cost-tally (6), excel-upload (5), persistent-dataset-browser (2).

---

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Backend is minimal but REAL on the one core path (no fake data on the tested path). Frontend is visually complete: real UI for the working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Later phases wire those stubs into real functionality, one increment at a time.

### Phase 1 — Upload → Profile → Ask → Answer (with chart, table, show-its-work)

- **Goal:** The full primary journey, working the first time: upload a CSV, see an auto-profile, ask ONE natural-language question, and get a plain-English answer + key numbers + ONE auto-picked chart + a summary table, with the plan / step trace / exact DuckDB SQL visible (collapsible), dialect-safe with retry-on-SQL-error, and the run logged to SQLite. All other features visible as labelled stubs.
- **Independent slices (parallel build units):** default all independent; the one declared dependency is noted.
  - `db-migration` (backend) — SQLAlchemy models + Alembic migration for `datasets` and `question_runs`; deps: none.
  - `analysis-engine` (backend) — DuckDB local execution: CSV ingest to a local DuckDB file, schema extraction, profile computation, dialect-safe SQL execution with the schema/aggregate-only contract; deps: none (pure module, no graph).
  - `agent-graph` (backend) — the LangGraph nodes/edges (plan → privacy-guard → generate-SQL → execute → observe/retry → phrase-answer → pick-chart → finalize), the `AnalystState`, prompts, runner; deps: **uses `analysis-engine`'s functions** (calls them, does not redefine) and **persists via `db-migration`'s models** — declared dependency, so build `analysis-engine` + `db-migration` first, then `agent-graph`.
  - `api-routes` (backend) — `POST /datasets` (upload+profile), `GET /datasets/{id}`, `POST /datasets/{id}/ask`; deps: calls `agent-graph`'s runner + `db-migration` models. Declared dependency on those two.
  - `frontend-ui` (frontend) — the upload→profile→ask→answer screen, chart render, summary table, collapsible show-its-work, and ALL labelled stubs; deps: none (codes against the API contract in `spec/api.md`; can build in parallel against the documented envelope).
  - `e2e-tests` (frontend) — Playwright smoke test of the primary journey; deps: needs `frontend-ui` + `api-routes` at gate time (runs last).
- **Key surfaces / files:**
  - `db-migration`: `src/db/models.py` (add `DatasetRow`, `QuestionRunRow`), `alembic/versions/0002_datasets_runs.py`.
  - `analysis-engine`: `src/analysis/__init__.py`, `src/analysis/duckdb_engine.py` (ingest, schema, profile, execute), `src/analysis/profile.py`, `src/analysis/charts.py` (chart-type heuristic on aggregate result).
  - `agent-graph`: `src/graph/state.py` (replace `AgentState` → `AnalystState`), `src/graph/nodes.py` (replace `transform_text` with the analyst nodes), `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/runner.py`, `src/prompts/plan.md`, `src/prompts/generate_sql.md`, `src/prompts/phrase_answer.md` (delete `src/prompts/transform.md`).
  - `api-routes`: `src/api/datasets.py` (new router), `src/api/__init__.py` (include router), `src/domain/dataset.py` (request/response models); leave `src/api/runs.py` in place or remove — see Assumed below.
  - `frontend-ui`: `frontend/src/app/page.tsx` (replace transform form), `frontend/src/components/*` (Uploader, ProfileCard, AskBox, AnswerPanel, Chart, SummaryTable, ShowItsWork, StubPanel).
  - `e2e-tests`: `frontend/tests/e2e/primary-journey.spec.ts`, `frontend/playwright.config.ts`, `frontend/package.json` (add `@playwright/test`).
  - `pyproject.toml`: add `duckdb>=1.1` dependency (call-out for the `analysis-engine` generator).
- **Gate command:** `uv run alembic upgrade head && uv run pytest` (runs against real Gemini via `.env` `AGENT_GEMINI_API_KEY` and the real DuckDB + SQLite drivers; integration tests upload a fixture CSV large enough that a sampled answer differs from the full-data answer, ask a real question, and assert the answer, the executed SQL, the trace, and that no raw row appears in any logged LLM input). Frontend gate: `cd frontend && pnpm build && pnpm exec playwright test` (the Phase-1 E2E smoke against the running app).
- **How the user tests it (handoff seed):**
  1. Run `cd frontend && pnpm build` then `uv run python -m src`. Open `http://localhost:8001/app/`.
  2. Click upload and pick a CSV (e.g. sales by region/month). Expect a profile card: row count, each column's name + inferred type, and a null/health summary — within ~30s. (REAL)
  3. Type a question, e.g. "Which region had the highest total sales?" Press Ask. Expect: a plain-English answer with the key number called out, ONE chart (auto-picked), and a small summary table — within ~30s. (REAL)
  4. Expand "Show its work": see the plan, the step trace (any failed-then-retried SQL is shown), and the exact DuckDB SQL that ran. (REAL)
  5. Labelled STUBS (visibly greyed / "coming soon", must not look broken): the dataset list in the sidebar (single current dataset only), "follow-up question" box, "suggested questions" chips, "compare another file" button, "column notes" panel, and the daily-cost figure (shows "—"). Per-question cost IS shown (REAL).

### Phase 2 — Persistent dataset browser (multi-day revisit)

- **Goal:** Datasets and their question history persist across sessions (they already do — Phase 1 logs them to SQLite); the user can pick a past dataset from the sidebar to re-open its profile and see/re-open its prior question runs (answer + chart + SQL/trace), and switching sets the active dataset for new questions. Wires the Phase-1 sidebar stub into real navigation. **No new table / migration** — Phase 2 only READS the Phase-1 `datasets` + `question_runs` tables (see [`data.md`](data.md)). **Privacy intact:** re-opening a past run renders from the persisted bounded record and does **no LLM call** (pure DB read; no raw rows anywhere).
- **Independent slices (parallel build units):** both independent — the frontend codes to the documented API contract in [`api.md`](api.md), so the two parallelize.
  - `datasets-api` (backend) — `GET /datasets` (list, newest first, with `question_count`) and `GET /datasets/{id}/runs` (history, newest first, each record reconstructed to the live `AskResult` shape via the same `_ask_payload`/`_chart_data` logic); deps: none (reads Phase-1 tables).
  - `dataset-browser-ui` (frontend) — real switchable sidebar list, dataset-switch (re-load profile via the existing `GET /datasets/{id}`), run-history list, and re-open-a-past-run into the existing `AnswerPanel`; deps: none (codes to the documented API).
- **Key surfaces / files:**
  - `datasets-api`: `src/api/datasets.py` (add `GET /datasets` and `GET /datasets/{id}/runs` routes), `src/graph/runner.py` (add `list_datasets()` and `get_dataset_runs(dataset_id)` — the latter reuses `_ask_payload`/`_chart_data` to rebuild each persisted run's `chart.data`/`table`, plus `question`/`created_at`), `src/domain/dataset.py` (add `DatasetSummary` + `RunRecord` response models).
  - `dataset-browser-ui`: `frontend/src/lib/api.ts` (add `getDatasets()` → `DatasetSummary[]` and `getDatasetRuns(id)` → `RunRecord[]`, where `RunRecord` extends the existing `AskResult` with `question` + `created_at`), `frontend/src/components/Sidebar.tsx` (replace the "Past datasets" stub with the real switchable list), `frontend/src/components/RunHistory.tsx` (new — per-dataset run list + re-open), `frontend/src/app/page.tsx` (wire dataset-switch + re-open-run into the existing profile card + `AnswerPanel`). Re-opening a run needs **no new render component** — the `RunRecord` shape is the `AskResult` the `AnswerPanel` already consumes.
- **Gate command:** `uv run pytest tests/integration/test_dataset_browser.py -q` (uploads two CSVs, asks a real question on each against real Gemini + DuckDB + SQLite, then asserts: `GET /datasets` lists both newest-first with correct `question_count`; `GET /datasets/{id}/runs` returns each run in the `AskResult` shape with `chart.data`/`table` reconstructed identically to the live ask and `question`/`created_at` present; `GET /datasets/{missing}/runs` → 404; an existing dataset with no runs → `200` + `[]`; and that fetching history makes **no LLM call**) **and** `cd frontend && pnpm exec playwright test tests/e2e/dataset-browser.spec.ts` (the dataset-browser E2E smoke against the running app).
- **How the user tests it:** Upload two CSVs across the session. The sidebar now lists both (newest first, with name · rows · question count) — REAL. Click the older dataset: its profile card re-loads and its past questions appear. Click a past question: its full answer + chart + table + show-its-work re-open instantly (no new question asked). Ask a new question on the active dataset: it appends to the top of the history. (Follow-ups, compare, Excel/notes, suggestions/daily-cost remain labelled "coming soon" stubs — REAL only for the browser.)

### Phase 3 — Conversational follow-ups (turn memory)

- **Goal:** Ask many follow-up questions on a loaded dataset; the agent remembers the conversation and the dataset context. Wires the Phase-1 follow-up stub.
- **Independent slices (parallel build units):**
  - `conversation-state` (backend) — message-history persistence + injecting prior turns into the plan/SQL prompts; deps: none (extends `AnalystState` + a `messages` table).
  - `chat-ui` (frontend) — turn-based chat surface replacing the single-question box; deps: none (API contract).
- **Key surfaces / files:** backend `src/db/models.py` (`MessageRow`), `alembic/versions/0003_messages.py`, `src/graph/nodes.py` (context injection), `src/graph/state.py`; frontend `frontend/src/components/Conversation.tsx`.
- **Gate command:** `uv run pytest tests/integration/test_conversation.py` (asks a question, then a follow-up that only resolves correctly if prior-turn context is used — e.g. "and which was lowest?" — against real Gemini + DuckDB) and the matching Playwright spec.
- **How the user tests it:** Ask a question, then a pronoun/elliptical follow-up; the answer correctly uses the earlier turn's context.

### Phase 4 — Multi-file compare / JOIN

- **Goal:** Load two datasets and ask a question that spans both (JOIN/compare). Wires the Phase-1 "compare another file" stub.
- **Independent slices (parallel build units):**
  - `multi-table-engine` (backend) — register multiple CSVs as DuckDB tables, schema bundle across tables, JOIN-aware SQL generation; deps: none.
  - `compare-ui` (frontend) — second-file picker + cross-dataset question UI; deps: none.
- **Key surfaces / files:** backend `src/analysis/duckdb_engine.py` (multi-table registration), `src/prompts/generate_sql.md` (multi-table schema), `src/api/datasets.py` (ask-across endpoint); frontend `frontend/src/components/ComparePicker.tsx`.
- **Gate command:** `uv run pytest tests/integration/test_multi_file.py` (two related CSVs, a JOIN question, asserts the joined answer against real engine + LLM) and the matching Playwright spec.
- **How the user tests it:** Upload two related files, ask a question that needs both, get a correct joined answer.

### Phase 5 — Excel upload + column-notes / business-rule memory

- **Goal:** Accept `.xlsx` uploads, and let the user attach column notes / business rules that the agent uses when planning. Wires the Phase-1 Excel and column-notes stubs.
- **Independent slices (parallel build units):**
  - `excel-ingest` (backend) — `.xlsx` → DuckDB ingest (sheet pick, type coercion); deps: none.
  - `notes-memory` (backend) — persist column/business-rule notes per dataset, inject into prompts; deps: none.
  - `notes-ui` (frontend) — Excel upload enablement + notes editor; deps: none.
- **Key surfaces / files:** backend `src/analysis/excel_ingest.py`, `pyproject.toml` (add `openpyxl`), `src/db/models.py` (`NoteRow`), `alembic/versions/0004_notes.py`, `src/prompts/plan.md`; frontend `frontend/src/components/NotesEditor.tsx`.
- **Gate command:** `uv run pytest tests/integration/test_excel_and_notes.py` (uploads an `.xlsx`, attaches a business-rule note, asks a question whose correct answer depends on the note — real engine + LLM) and the matching Playwright spec.
- **How the user tests it:** Upload an Excel file, add a column note (e.g. "revenue is in thousands"), ask a question that needs the note, get a note-aware answer.

### Phase 6 — Suggested follow-ups, clarifying-question gate, daily-cost tally

- **Goal:** Proactive UX: after each answer suggest 2–3 follow-up questions, ask a clarifying question when a request is ambiguous, and show a running daily cost total. Wires the remaining Phase-1 stubs.
- **Independent slices (parallel build units):**
  - `suggestions-node` (backend) — a cheap LLM call (or template) producing 2–3 follow-up suggestions from the answer; deps: none.
  - `clarify-gate` (backend) — a confidence/ambiguity check node that pauses for a clarifying question; deps: none.
  - `cost-rollup` (backend) — daily cost aggregation endpoint; deps: none (reads Phase-1 cost column).
  - `proactive-ui` (frontend) — suggestion chips, clarifying-question prompt, daily-cost figure; deps: none.
- **Key surfaces / files:** backend `src/graph/nodes.py` (suggest + clarify nodes), `src/graph/edges.py` (clarify branch), `src/api/datasets.py` (cost endpoint); frontend `frontend/src/components/Suggestions.tsx`, `frontend/src/components/DailyCost.tsx`.
- **Gate command:** `uv run pytest tests/integration/test_proactive.py` (ambiguous question triggers a clarifying question; a clear one yields suggestions; cost endpoint sums the day — real LLM + DB) and the matching Playwright spec.
- **How the user tests it:** Ask an ambiguous question and get a clarifying prompt; ask a clear one and see 2–3 suggested follow-ups plus a non-zero daily cost total.

> **Assumed:** The skeleton's `transform_text` capability and its `/runs` endpoint are **replaced**, not kept. The `runs` table/route are superseded by `datasets` + `question_runs`. The Phase-1 `agent-graph` slice rewrites `src/graph/*` and `db-migration` adds the new tables; `src/api/runs.py` and `src/prompts/transform.md` are removed, and `tests/integration/test_pipeline.py` is rewritten to the analyst pipeline. Existing unit tests for settings/db/api are updated to the new surface.
