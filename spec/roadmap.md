# Roadmap

> Personal Data Analysis Agent — a browser-based, code-execution data analyst for a single power user.

---

## What This Agent Does

A personal, browser-based data-analysis agent. The user uploads a CSV/Excel file and asks plain-language questions about it. A real code-execution agent loop (LangGraph) plans the analysis, writes Python/pandas (or SQL) code, runs that code **locally on the full dataset**, and iterates (revise + re-run on error) until the result is correct. Every answer comes back as plain-language prose with key numbers, an auto-selected interactive chart (zoom/hover/filter), and the underlying summary table — plus a collapsible code panel showing the exact code that produced it, a transparency panel showing exactly what was sent to the LLM, and a per-question cost/token readout. The agent persists run history, conversation, datasets, and usage so the user can return across days.

## Who Uses It

A single technical power user (the owner) who works with their own data frequently and wants a trustworthy, low-friction analyst they can act on. They are comfortable with code, want to **see the exact code** behind any answer, and care about keeping LLM cost low. There is no multi-tenant access, no auth, no external sharing.

## Core Problem Being Solved

Answering arbitrary, open-ended questions over a fresh dataset normally means hand-writing pandas/SQL, building a chart, and re-checking the numbers — repeatedly, every time the question changes. Off-the-shelf "chat with your data" tools either ship the whole dataset to an LLM (a privacy problem and a cost problem) or map questions onto a rigid hardcoded op-list that fails silently on anything unanticipated. This agent writes and runs real code locally on the full data, shows that code, and keeps only schema + tiny samples + small aggregates in front of the LLM.

## Success Criteria

- [ ] A user uploads a CSV (up to ~100MB) and gets a correct plain-language answer + interactive chart + summary table to a plain-language question in **under ~30s** on the happy path.
- [ ] The generated code **runs locally on the full dataset**; the LLM payload for any run contains only schema + ≤20 sample rows + small aggregated results — verifiable in the transparency panel and asserted by an automated test (no bulk-data bytes leave the local process to the LLM).
- [ ] Every answer surfaces the **exact code** that produced it (collapsible code panel) and the **exact LLM payload** (transparency panel).
- [ ] Every answer displays a **per-question cost estimate + token counts (in/out)**, computed from the real provider usage.
- [ ] On a code error, the agent **revises and re-runs** automatically (up to a capped number of iterations) and either succeeds or returns a flagged best-guess showing what it tried.

## What This Agent Does NOT Do (Out of Scope)

- No multi-tenant access, user accounts, or authentication (single local user).
- No external integrations — no Slack, email, webhooks, or cloud sync.
- No sending of bulk dataset rows to the LLM, ever (firm privacy boundary).
- No remote/managed analysis compute — code runs locally only.
- No write-back to source systems or live production databases.
- No model fine-tuning or training on user data.
- No scheduled/automated runs — every analysis is user-initiated.

## Key Constraints

- **Privacy boundary (firm, holds from Phase 1):** code executes locally on the full dataset; the LLM only ever receives schema + a small sample (≤20 rows) + small aggregated results. The UI surfaces exactly what was sent.
- **Performance:** CSV/Excel up to ~100MB; happy-path answer in under ~30s.
- **Cost:** keep LLM cost low — per-question cost/token readout + running daily total; use the cheaper Gemini tier for routine nodes.
- **Single local user, single origin:** app served at `http://localhost:8001/app/`; backend on port 8001; no auth.
- **Stack is fixed (intake):** Python + FastAPI + LangGraph backend, Next.js static-export frontend, **DuckDB** for local analysis compute, **SQLite** (via SQLAlchemy) for app state, **Gemini** LLM (`AGENT_GEMINI_API_KEY` already in `.env`).
- **Local code execution is trusted-user, in-process:** generated code runs in a constrained local execution context (see `architecture.md`), not a hardened multi-tenant sandbox — acceptable because the only user is the local owner running their own data.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is minimal but REAL on the one core path (no fake data on the tested path). Its frontend is visually complete: real UI for the one working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Each later phase wires those stubs into real functionality, one increment at a time.

> **Assumed:** dataset auto-profile-on-load is **deferred to Phase 2**. Phase 1 computes schema + sample + dtypes on upload (the minimum the privacy boundary and code-gen need), but the rich profile UI (ranges, missing-counts, distributions) is a labelled stub in Phase 1 — it is not on the smallest core path (upload → ask → answer) and adding the full profile UI would over-build Phase 1.

> **Assumed:** live token-by-token answer **streaming** is deferred to Phase 3. Phase 1 shows discrete, non-streamed progress stages ("Planning… / Writing code… / Running… / Building chart…") that update as the run completes its stages via a polled run-status endpoint; the streaming label in the UI is marked "coming soon". This keeps Phase 1 first-time-right without an SSE/static-export integration risk on the smallest win.

### Phase 1 — Upload + Ask + Answer (the core code-execution loop)

- **Goal:** The user uploads one CSV, asks a plain-language question, and the LangGraph agent writes & runs pandas code **locally on the full file** (privacy boundary held), returning plain-language answer + auto-picked interactive chart + summary table, with a collapsible code panel (exact code), a transparency panel (exact LLM payload), and per-question cost (tokens in/out + estimate). One revise-on-error retry is wired.
- **Independent slices (parallel build units):**
  - `db-schema` (backend) — SQLAlchemy models for `datasets`, `runs`, plus schema-only stub tables (`sessions`, `cost_log`, `conversation`, `column_notes`, `saved_datasets`, `analysis_library`); Alembic migration. deps: none
  - `analysis-engine` (backend) — DuckDB/pandas local execution module: file ingest → DuckDB table + parquet, schema/sample extraction, constrained `exec` of generated code on the full frame, result capture. deps: none (consumed by `graph-loop` at runtime, but built against a defined interface so it builds in parallel)
  - `graph-loop` (backend) — replace `transform_text` with the data-analysis LangGraph: `profile → plan → generate_code → execute_locally → (revise loop) → summarize → select_chart`; AgentState, nodes, edges, runner; prompts; cost/token accounting; privacy-redaction point. deps: declares the `analysis-engine` interface (`src/analysis/engine.py` function signatures) — code-generators agree the signature up front so both build concurrently
  - `api-routes` (backend) — `POST /datasets` (upload), `POST /analyses` (ask), `GET /analyses/{id}`, `GET /datasets/{id}`; envelopes; wires `run_agent`. deps: uses the `graph-loop` runner + `db-schema` models (interface agreed up front)
  - `frontend` (frontend) — single-page app: upload zone, question box, answer panel (prose + key numbers), interactive Plotly chart, summary table, collapsible code panel, transparency panel, per-question cost display, simple staged progress; clearly-labelled stub regions for all deferred features. deps: none (builds against the `api.md` contract)
- **Key surfaces / files:** `src/db/models.py`, `alembic/versions/*`; `src/analysis/engine.py`, `src/analysis/storage.py`; `src/graph/{state,nodes,edges,agent,runner}.py`, `src/prompts/{plan,generate_code,summarize,select_chart}.md`, `src/analysis/cost.py`; `src/api/{datasets,analyses}.py`, `src/domain/*`; `frontend/src/app/page.tsx`, `frontend/src/components/*`, `frontend/src/lib/api.ts`, `tests/e2e/`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/phase1 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q`
  - The pytest suite calls the **real Gemini API via `.env`** and runs generated pandas code on a **real ≥250k-row CSV fixture** (large enough that a sampled answer ≠ a full-data answer — the gate asserts the full-data answer). Playwright E2E runs against the live app at `http://localhost:8001/app/`.
- **How the user tests it (handoff seed):**
  1. `cp .env.example .env` (confirm `AGENT_GEMINI_API_KEY` is set), `uv sync`, `cd frontend && pnpm install && pnpm build && cd ..`, then `uv run alembic upgrade head`, then `uv run python -m src`.
  2. Open `http://localhost:8001/app/`.
  3. Drag-drop a CSV into the upload zone (a sample `data/sample/sales.csv` is provided). Wait for "Dataset loaded".
  4. Type a question, e.g. *"What were total sales by month, and which month was highest?"*, press Ask.
  5. **Expected (REAL):** staged progress runs, then an answer panel with prose + key numbers, an interactive Plotly chart (hover/zoom), a summary table, a collapsible "Show code" panel with the exact pandas code, a "What was sent to the LLM" panel (schema + sample + aggregates only — no bulk rows), and a cost line ("~$0.00X · 1,2xx in / 3xx out tokens").
  6. **Labelled STUBS (visible, non-functional, marked "Coming soon"):** "Connect a database", "Join multiple files", "Saved sessions", "Column notes & business rules", "Follow-up suggestions", "Export", "Saved datasets", "Analysis library", "Daily cost total", "Live streaming". A stub never errors — it shows a disabled/coming-soon state.

### Phase 2 — Sessions, Persistent Memory & Dataset Profile

- **Goal:** The user returns across days to a persistent session that carries conversation history, keeps loaded datasets loaded, and shows a rich auto-profile of each dataset on load. Follow-up suggestions appear after each answer.
- **Independent slices (parallel build units):**
  - `sessions-backend` (backend) — real `sessions` + `conversation` tables; session create/list/resume; conversation log written per turn; conversation history threaded into the `plan` node prompt. deps: none
  - `profile-node` (backend) — real `profile` node + endpoint: full column profile (types, ranges, missing counts, cardinality, top values) computed in DuckDB on load; persisted. deps: none
  - `followups-node` (backend) — `suggest_followups` node (real) appended to the graph after `summarize`; returns 2–3 suggested questions. deps: none
  - `frontend` (frontend) — session sidebar (list/resume/new), conversation thread view, dataset profile panel (wires the Phase-1 stub), clickable follow-up chips. deps: none (builds against `api.md`)
- **Key surfaces / files:** `src/db/models.py` (activate stub tables), `alembic/versions/*`, `src/api/sessions.py`, `src/graph/nodes.py` (profile, suggest_followups, history threading), `src/prompts/{profile,followups}.md`, `frontend/src/components/{SessionSidebar,ConversationThread,ProfilePanel,FollowupChips}.tsx`, `tests/phase2`, `tests/e2e`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/phase2 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q`
  - Asserts: a second question in a session sees the first question's context (real conversation memory, not stateless); profile values match DuckDB ground truth on the large fixture; follow-ups returned from the real LLM.
- **How the user tests it (handoff seed):** Restart the app; open the app; the prior session is listed in the sidebar with its loaded dataset and conversation. Resume it; ask a follow-up that refers to "that" from the previous answer — it resolves correctly. Open the dataset profile panel — real column stats. Click a suggested follow-up chip — it asks that question. STUBS still labelled: DB connect, joins, column notes, export, saved datasets, analysis library, daily total, streaming.

### Phase 3 — Cost Rollup, Live Streaming & Column Notes / Business Rules

- **Goal:** Live streaming progress (answer streams as it forms), a running daily cost total, and user-supplied column notes & business rules that the agent honours ("revenue excludes refunds").
- **Independent slices (parallel build units):**
  - `streaming-backend` (backend) — SSE endpoint streaming staged progress + token-by-token answer from the `summarize` node; cost events. deps: none
  - `cost-rollup` (backend) — real `cost_log` writes per run + daily aggregation endpoint. deps: none
  - `notes-backend` (backend) — real `column_notes` table + endpoints; notes/business rules injected into `plan` + `generate_code` prompts. deps: none
  - `frontend` (frontend) — streamed answer rendering (EventSource), daily-total widget, column-notes editor; wires the Phase-1 stubs. deps: none
- **Key surfaces / files:** `src/api/{stream,cost,notes}.py`, `src/graph/runner.py` (event emission), `src/db/models.py` (activate cost_log, column_notes), `frontend/src/components/{StreamingAnswer,DailyCost,ColumnNotesEditor}.tsx`, `tests/phase3`, `tests/e2e`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/phase3 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q`
  - Asserts: SSE stream emits ordered stage events + answer chunks; daily total = sum of run costs for the day; a business rule ("exclude refunds") provably changes the generated code/result vs. without the note.
- **How the user tests it (handoff seed):** Ask a question — watch the answer stream in live with stage labels. The daily-total widget increments. Add a column note ("`amount` is in cents") and a rule ("revenue excludes rows where `status='refunded'`"); re-ask — the answer and code reflect the rule. STUBS still labelled: DB connect, joins, export, saved datasets, analysis library.

### Phase 4 — Output Lifecycle: Export, Saved Datasets & Analysis Library

- **Goal:** In-app export (CSV / chart image / report), saving a derived result as a reusable dataset, and a library of past analyses to revisit and re-run.
- **Independent slices (parallel build units):**
  - `export-backend` (backend) — export endpoints (result CSV, chart PNG, run report). deps: none
  - `saved-datasets-backend` (backend) — real `saved_datasets` table; persist a derived result as a new DuckDB table reusable as a source in later questions. deps: none
  - `library-backend` (backend) — real `analysis_library` (built on `runs`); list/re-run a past analysis. deps: none
  - `frontend` (frontend) — export buttons, "save as dataset" action, analysis-library view with re-run; wires the Phase-1 stubs. deps: none
- **Key surfaces / files:** `src/api/{export,saved_datasets,library}.py`, `src/analysis/storage.py` (derived tables), `src/db/models.py` (activate saved_datasets), `frontend/src/components/{ExportMenu,SaveDataset,AnalysisLibrary}.tsx`, `tests/phase4`, `tests/e2e`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/phase4 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q`
  - Asserts: export produces a valid CSV/PNG/report; a saved derived dataset is queryable as a source in a new analysis; a library entry re-runs and reproduces its result.
- **How the user tests it (handoff seed):** Export an answer's table as CSV and the chart as PNG. Save a derived result ("monthly_totals") and ask a new question against it. Open the analysis library, re-run a past analysis — same result. STUBS still labelled: DB connect, multi-file joins.

### Phase 5 — Connected Database & Multi-File Joins

- **Goal:** Connect a local DuckDB/SQLite database as a source, and load multiple files with auto-inferred join relationships, so questions span multiple tables.
- **Independent slices (parallel build units):**
  - `db-connect-backend` (backend) — attach a local DuckDB/SQLite file as a read-only analysis source; schema discovery. deps: none
  - `joins-backend` (backend) — multi-file upload; auto-infer relationships (key overlap / name+type heuristics); expose inferred joins to the `plan`/`generate_code` nodes. deps: none
  - `frontend` (frontend) — "Connect a database" flow, multi-file dataset view with inferred-relationship display + override; wires the final Phase-1 stubs. deps: none
- **Key surfaces / files:** `src/api/{connections,joins}.py`, `src/analysis/{engine,relationships}.py`, `src/db/models.py`, `frontend/src/components/{ConnectDatabase,MultiFileJoins}.tsx`, `tests/phase5`, `tests/e2e`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/phase5 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q`
  - Asserts: a connected DuckDB/SQLite source is queryable; two uploaded files with a shared key produce a correct joined answer; inferred relationship matches ground truth.
- **How the user tests it (handoff seed):** Connect a local `.duckdb`/`.sqlite` file — its tables appear as sources. Upload two related CSVs (`orders.csv`, `customers.csv`); the app shows the inferred join (`orders.customer_id → customers.id`); ask a question spanning both — correct joined answer. No stubs remain — every capability is real.
