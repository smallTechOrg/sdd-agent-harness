# Roadmap

A personal, local-first data-analysis agent. See [`architecture.md`](architecture.md) for the stack and how the privacy boundary, plan-then-execute flow, and cost guard work; see [`agent.md`](agent.md) for the LangGraph graph.

---

## What This Agent Does

This agent lets a single person analyse their own CSV/Excel files in plain language, on their own machine, without their raw data ever leaving it. The user uploads a file, asks a question in everyday language ("which region had the highest average order value?"), and gets back a written answer with the key numbers, a result table, and — over later phases — interactive charts and smart follow-ups. Crucially, the full dataset is never sent to the LLM: the model only ever sees the column schema plus a few sample rows, writes analysis code, and that code runs locally against the full data via DuckDB/pandas. The agent plans an analysis strategy first, then executes it step by step under a hard step cap so cost stays low and predictable, and it shows its work — the plan, the code it ran, each intermediate result, and the exact token/cost for every question.

## Who Uses It

A single technical-but-busy individual — an analyst, founder, operator, or researcher — who keeps a personal library of spreadsheets and repeatedly needs quick, trustworthy answers from them. They are willing to "act on these answers", so accuracy and a visible audit trail matter more than polish. They run the tool locally for themselves; there is no multi-user, no auth, no team.

## Core Problem Being Solved

Today this person either writes ad-hoc pandas/SQL by hand (slow, repetitive) or pastes data into a cloud chatbot (a privacy non-starter for real data, and it silently samples or truncates large files, giving wrong answers). This agent replaces both: plain-language questions over the **full** local dataset, correct because the code runs on all rows, private because raw data never leaves the machine, and auditable because every answer ships with its plan, code, and cost.

## Success Criteria

- [ ] User uploads a CSV (up to ~100MB), asks a plain-language question, and gets a correct plain-language answer plus key numbers and a result table, in under 30s for typical aggregate questions.
- [ ] The full dataset is analysed locally (DuckDB/pandas); the LLM payload for any question contains only the schema plus ≤ N sample rows — verifiable from the audit trail, never the full data.
- [ ] Every answer shows the plan the agent made, the code it ran (collapsible), and the per-question cost (tokens in/out + estimated USD).
- [ ] The step cap holds: no question exceeds the configured max reasoning/execution steps; when the cap is hit, the user is warned rather than the agent spending freely.
- [ ] Answers are correct on full data, not a sample — a question whose answer differs between a 1000-row sample and the full file returns the full-file answer.

## What This Agent Does NOT Do (Out of Scope)

- No multi-user, authentication, accounts, or sharing — single local user only.
- No external integrations (no databases, warehouses, cloud storage, BI tools, Slack, email).
- Never sends full data rows to the LLM — schema + bounded sample rows only.
- No write-back / data mutation — the agent reads and analyses; it never edits the source files.
- No model fine-tuning or learning from feedback.
- No deployment to a server / cloud — it is a local-first personal tool.
- v1 does not do streaming token-by-token answer rendering of the LLM (it streams *step* updates; token streaming is out of scope).
- Excel beyond simple single-sheet `.xlsx` is out of scope (CSV-first; basic Excel only, deferred to a later phase).

## Key Constraints

- **Privacy boundary (core architectural constraint):** raw data stays on the machine; the LLM sees only schema + a bounded number of sample rows. Full data is processed locally via DuckDB + pandas. See [`architecture.md`](architecture.md#privacy-boundary).
- **Cost guard (hard requirement):** a hard cap on reasoning/execution steps per question; exceeding it warns the user instead of spending freely. Default Flash-tier Gemini model for low cost.
- **Scale / latency:** CSV files up to ~100MB; target answers under 30s for typical aggregate questions.
- **Reliability:** production-quality accuracy ("I will act on these answers") plus a lightweight audit trail (question+answer log; per-run code/results viewable).
- **Local-only:** runs single-origin on `http://localhost:8001/app/`; SQLite for app state/history; no network egress except the Gemini API call.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is minimal but REAL on the one core path (no fake data on the tested path). Its frontend is visually complete: real UI for the one working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Each later phase wires those stubs into real functionality, one increment at a time.

Capabilities (see [`capabilities/index.md`](capabilities/index.md)) map to phases as: **analyze_question** → Phase 1; **profile_dataset** + **suggest_followups** → Phase 2; **interactive_charts** → Phase 3; **persistent_library_history** + **multi_file_analysis** → Phase 4.

### Phase 1 — Ask one CSV, get a correct answer with plan + code + cost

- **Goal:** Upload one CSV → ask a plain-language question → get a CORRECT plain-language answer + key numbers + a result table, showing the PLAN the agent made, the CODE it ran (collapsible), and the COST (tokens + estimated USD) for that question. The LangGraph plan-then-execute graph with the step-cap cost guard is wired and real, even if replan/multi-step is minimal. Privacy boundary holds: schema + ≤ N sample rows to the LLM only; full CSV analysed locally via DuckDB. Structured observability (structlog) emits a line per run. This is the only real path; everything else is a labelled stub.

- **Independent slices (parallel build units):**
  - `db-schema` (backend) — Alembic migration + SQLAlchemy models for the Phase 1 tables (`datasets`, `questions`, `analysis_steps`, `cost_records`); extends `db/models.py`. Deps: none. **Other backend slices depend on this slice's models existing**, so it lands first; in practice all backend slices are written together by one generator if the fan-out is small, but the file seams are disjoint so they can split.
  - `analysis-engine` (backend) — the local DuckDB/pandas execution sandbox: load a CSV into DuckDB, run LLM-generated SQL/pandas safely, return bounded aggregated results + schema/sample-row extraction. Owns `analysis/` (new package). Deps: none (pure local engine, no DB, no graph).
  - `agent-graph` (backend) — replace the `transform_text` slot with the plan-then-execute graph: `plan → execute_step (loop) → step_cap_check/replan → synthesize_answer`, state type, cost accumulation, error handler, finalize. Owns `graph/{state,nodes,edges,agent,runner}.py` and `prompts/`. Deps: `analysis-engine` (calls it from `execute_step`).
  - `api-routes` (backend) — `POST /datasets` (upload CSV), `POST /questions` (ask → run graph → persist), `GET /questions/{id}` (full answer payload: answer, plan, steps+code, cost). Owns `api/datasets.py`, `api/questions.py`, domain models. Deps: `db-schema`, `agent-graph`.
  - `frontend` (frontend) — replace the transform form with: a file-upload + active-dataset bar, a question box, and an answer panel showing answer + key numbers + result table + collapsible plan + collapsible code + cost chip; PLUS labelled non-functional stubs for charts, library/history, follow-ups, multi-file, and daily cost total. Owns `frontend/src/app/page.tsx`, components, and `frontend/tests/e2e/`. Deps: none (builds against the documented API contract in parallel).

- **Key surfaces / files:**
  - Backend: `src/db/models.py`, `alembic/versions/<rev>_phase1.py`, `src/analysis/{__init__,engine,loader,profile}.py`, `src/graph/{state,nodes,edges,agent,runner}.py`, `src/prompts/{plan,execute,synthesize}.md`, `src/api/{datasets,questions}.py`, `src/domain/*.py`, `src/config/settings.py` (add cost/step-cap/sample-row settings), `src/observability/events.py`.
  - Frontend: `frontend/src/app/page.tsx`, `frontend/src/components/{UploadBar,QuestionBox,AnswerPanel,PlanView,CodeView,CostChip,StubCard}.tsx`, `frontend/tests/e2e/phase1.spec.ts`.
  - Tests: `tests/test_phase1_*.py` (engine on full vs sampled data, graph end-to-end on real Gemini, privacy-payload assertion, API contract).

- **Gate command:** `uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm build) && npx playwright test frontend/tests/e2e/ --reporter=line`
  - Runs against the real Gemini Flash model via `AGENT_GEMINI_API_KEY` in `.env`, SQLite driver (production driver here is SQLite). The pytest suite MUST include a full-data-vs-sample test using a fixture large enough that the sampled answer and the full-data answer differ (see [data-processing gate note](#data-gate)), and a privacy test asserting the LLM payload never contains full data rows.

- **How the user tests it (handoff seed):**
  1. `cd frontend && pnpm build` then `uv run python -m src` from the repo root; open `http://localhost:8001/app/`.
  2. Click **Upload CSV**, pick a real CSV (e.g. a 50–100MB orders/sales file). The active-dataset bar shows the file name, row count, and column count.
  3. Type a question, e.g. "What is the total revenue by region, highest first?" and press **Ask**.
  4. Expect: a plain-language answer with the key numbers, a result table of regions × revenue, an expandable **Plan** (the strategy the agent drafted), an expandable **Code** (the SQL/pandas it ran), and a **Cost** chip (tokens in/out + estimated USD). Live step updates appear while it runs.
  5. **Real on this path:** upload, ask, answer, key numbers, result table, plan, code, cost, step updates.
  6. **Labelled stubs (must not look like bugs):** the "Charts" tab, the "Library & History" sidebar, the "Suggested follow-ups" row, the "Add another file / compare" control, and the "Daily cost total" badge each render with a visible "Coming in a later phase" label and are inert.

<a id="data-gate"></a>
> **Data-gate note:** the Phase 1 pytest fixture CSV must be large enough (e.g. ≥ 200k rows with a skewed tail) that an answer computed on a 1000-row sample is numerically different from the answer on the full file. The gate asserts the agent returns the **full-file** number. A fixture small enough that sample == full proves nothing.

### Phase 2 — Auto-profile on upload + smart follow-up suggestions

- **Goal:** When a file is uploaded it is auto-profiled (per-column type, ranges/min-max, null counts, distinct counts, obvious data-quality flags) and the profile is shown in the dataset bar. After every answer the agent suggests 2–3 smart, clickable follow-up questions. Wires the Phase 1 profile/follow-up stubs into real features.

- **Independent slices (parallel build units):**
  - `profiling-engine` (backend) — extend `analysis/profile.py` to compute a full column profile via DuckDB; persist to a `dataset_profiles` table (new migration). Owns `analysis/profile.py`, migration. Deps: none.
  - `followups-node` (backend) — add a `suggest_followups` graph node (one cheap LLM call after synthesize) that proposes 2–3 follow-ups from the question + result schema; persist to `questions`. Owns `graph/nodes.py` (additive), `prompts/followups.md`. Deps: none on profiling.
  - `api-extend` (backend) — `GET /datasets/{id}/profile`; include follow-ups in the answer payload. Owns `api/datasets.py`, `api/questions.py` (additive). Deps: profiling-engine, followups-node.
  - `frontend` (frontend) — make the profile panel and follow-up chips real (clickable follow-up re-asks). Owns frontend components + e2e. Deps: none (contract-driven).

- **Key surfaces / files:** `src/analysis/profile.py`, `alembic/versions/<rev>_profiles.py`, `src/graph/nodes.py`, `src/prompts/followups.md`, `src/api/{datasets,questions}.py`, `frontend/src/components/{ProfilePanel,FollowupChips}.tsx`, `frontend/tests/e2e/phase2.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && npx playwright test frontend/tests/e2e/ --reporter=line` (real Gemini via `.env`, SQLite).
- **How the user tests it (handoff seed):** Upload a CSV → the dataset bar now shows a real column profile (types, ranges, nulls, quality flags). Ask a question → below the answer, 2–3 real follow-up chips appear; clicking one asks it. Stubs remaining: charts, library/history, multi-file, daily cost total.

### Phase 3 — Interactive charts

- **Goal:** Answers that lend themselves to visualisation render an interactive chart (zoom/hover/filter) alongside the table, driven by the locally-computed aggregate result. Wires the Phase 1 "Charts" stub into a real feature.

- **Independent slices (parallel build units):**
  - `chart-spec-node` (backend) — extend `synthesize_answer` to emit a chart spec (chart type + encodings) chosen by the LLM from the result schema; the **data** for the chart is the locally-computed aggregate (never full rows). Persist the spec + aggregate to `questions`/`analysis_steps`. Owns `graph/nodes.py` (additive), `prompts/synthesize.md`. Deps: none.
  - `api-extend` (backend) — include `chart_spec` + chart data in the answer payload. Owns `api/questions.py` (additive). Deps: chart-spec-node.
  - `frontend` (frontend) — real interactive chart component rendering the spec; zoom/hover/filter. Owns `frontend/src/components/ChartView.tsx`, e2e. Deps: none (contract-driven).

- **Key surfaces / files:** `src/graph/nodes.py`, `src/prompts/synthesize.md`, `src/api/questions.py`, `frontend/src/components/ChartView.tsx`, `frontend/tests/e2e/phase3.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && npx playwright test frontend/tests/e2e/ --reporter=line` (real Gemini via `.env`, SQLite).
- **How the user tests it (handoff seed):** Ask a question with a natural chart (e.g. "revenue by month") → an interactive chart renders next to the table; hovering shows values, you can zoom/filter. Stubs remaining: library/history, multi-file, daily cost total.

### Phase 4 — Persistent library, durable history & multi-file analysis

- **Goal:** The full personal experience: a managed file library that persists across days; browsable question+answer history (with plan/code/results per run) and the running daily cost total; conversation history that carries context within and across sessions; and multi-file questions where the agent picks the right file(s) and can join/compare across files on a shared key. This is the complete-agentic-system phase — every remaining stub becomes real.

- **Independent slices (parallel build units):**
  - `conversations-memory` (backend) — `conversations` table + thread memory wired into graph state (prior turns inform the plan); cross-session recall. Owns `graph/{state,nodes}.py` (additive), migration. Deps: none.
  - `library-history-api` (backend) — `GET /datasets`, `DELETE /datasets/{id}`, `GET /history`, `GET /questions/{id}` (full audit), `GET /cost/daily`. Owns `api/{datasets,questions,history,cost}.py`. Deps: conversations-memory (history references conversations).
  - `multi-file-node` (backend) — file-selection + cross-file join/compare: the planner ranks library files for the question; the engine joins across CSVs in DuckDB on a shared key. Owns `analysis/engine.py` (additive), `graph/nodes.py` (additive), `prompts/plan.md`. Deps: none.
  - `frontend` (frontend) — real library sidebar (list/select/delete), history browser, daily-cost badge, multi-file picker/compare UI, conversation thread view. Owns frontend components + e2e. Deps: none (contract-driven).

- **Key surfaces / files:** `alembic/versions/<rev>_conversations.py`, `src/graph/{state,nodes}.py`, `src/analysis/engine.py`, `src/prompts/plan.md`, `src/api/{datasets,questions,history,cost}.py`, `frontend/src/components/{LibrarySidebar,HistoryBrowser,DailyCostBadge,MultiFilePicker}.tsx`, `frontend/tests/e2e/phase4.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && npx playwright test frontend/tests/e2e/ --reporter=line` (real Gemini via `.env`, SQLite).
- **How the user tests it (handoff seed):** Upload several files; they persist in the library sidebar across restarts. Ask a question spanning two files on a shared key (e.g. join orders to customers) → the agent picks the right files and joins them locally. Revisit past answers in the history browser (plan/code/results intact); see the running daily cost total. Restart the app and confirm conversation history and files are still there. No stubs remain.
