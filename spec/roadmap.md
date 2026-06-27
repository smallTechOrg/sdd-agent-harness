# Roadmap

> DataChat — a personal data-analysis chat agent. Upload a CSV/Excel file, ask questions in plain language, get plain-language answers and an auto-chosen chart, with a hard privacy boundary: raw data rows never leave the machine.

---

## What This Agent Does

DataChat lets one person upload a spreadsheet (CSV or Excel) and ask questions about it in plain English — "what were total sales by region?", "now break that down by month". It replies with a plain-language answer and, when the question is comparative or trend-shaped, an automatically-chosen chart (bar, line, or pie). All computation over the data happens **locally on the machine**: only the dataset's *schema* (column names and types) and *aggregated results* (counts, sums, group-bys — small summary tables) are ever sent to the LLM. Raw data rows never leave the machine. It is a chat conversation that remembers recent turns so follow-up questions work.

## Who Uses It

A single, cost-conscious individual analyst running the app locally for ad-hoc data exploration. They are comfortable with spreadsheets but do not want to write SQL or pandas. They care that their data stays private (it never gets uploaded to a third-party LLM in raw form) and that the tool is cheap to run (minimal LLM tokens).

## Core Problem Being Solved

Today this person either writes spreadsheet formulas / pivot tables by hand, or pastes data into a general chatbot — which is both privacy-leaking (raw rows go to a third party) and unreliable for arithmetic. DataChat replaces that with a chat interface where the heavy lifting (the actual aggregation arithmetic) is done deterministically and locally, and the LLM is used only for what it is good at: understanding the question, deciding what to compute, and explaining the result in plain language.

## Success Criteria

- [ ] A user can upload a CSV or Excel (.xlsx) file and within a few seconds see its detected schema (column names + inferred types + row count).
- [ ] A user can ask a plain-language question about the uploaded data and receive a correct plain-language answer grounded in a locally-computed aggregation.
- [ ] When the question is comparative or trend-shaped, an appropriate chart (bar / line / pie) is auto-chosen and rendered inline; when it is not, no chart is forced.
- [ ] **Privacy boundary holds:** in the full Phase-1 flow, no raw data row is ever included in any payload sent to the LLM — only schema and aggregated result tables. This is verifiable in a test that inspects the exact LLM-bound payload.
- [ ] A follow-up question that refers to the previous turn ("break that down by month") is answered using conversation context, not as a cold question.

## What This Agent Does NOT Do (Out of Scope)

- **Never sends raw data rows to the LLM.** Only schema + aggregates. (This is a hard boundary, not a deferral.)
- Does not connect to a live database (Postgres/MySQL) in Phase 1 — deferred to a later phase.
- Does not surface unprompted/auto-discovered insights (anomalies, trends it found on its own) in Phase 1 — deferred.
- Does not let the user manually override the chart type in Phase 1 — the agent chooses; manual controls are deferred.
- Does not do multi-user accounts, auth, sharing, or collaboration — single local user only.
- Does not do data *editing* / write-back — read-only analysis.
- Does not retain deep long-term cross-session memory of analyses in Phase 1 — only recent in-conversation turns.

## Key Constraints

- **Privacy:** raw rows stay on the local disk; LLM payloads carry only schema + aggregate tables. Non-negotiable.
- **Cost-conscious:** minimize tokens to Gemini — send compact schema descriptions and small aggregate tables (cap rows in any aggregate table sent to the LLM), never raw data dumps.
- **Stack is fixed:** Python + FastAPI + LangGraph + SQLite (app metadata store), Gemini (`gemini-2.5-pro`), Next.js web chat UI. See [architecture.md → Stack](architecture.md#stack).
- **SQLite is the production database** for app metadata (datasets, conversations, messages). The "live database connection" in a later phase is a *separate analysis source*, not a replacement for this metadata store.
- Local single-process deployment: one long-running uvicorn service on port 8001.

> **Assumed:** `gemini-2.5-pro` is the default per the brief, but because the only LLM tasks are (a) translating a question + schema into an aggregation plan and (b) writing a short answer + picking a chart from a small aggregate table — both light reasoning over compact inputs — a cheaper/faster model (`gemini-2.5-flash`) would likely serve as well at lower cost. The model is env-configurable (`AGENT_LLM_MODEL`); the spec defaults to `gemini-2.5-pro` and notes flash as the recommended cost optimization to evaluate.

> **Assumed:** Excel support in Phase 1 covers `.xlsx` via openpyxl (first sheet only, header in row 1). Legacy `.xls` and multi-sheet selection are out of scope for Phase 1.

> **Assumed:** "Aggregation engine" is implemented with **pandas** (read CSV/Excel → DataFrame → groupby/agg). DuckDB was considered but pandas is simpler for this single-user, modest-file-size scope and keeps the dependency surface small. Files are assumed to fit comfortably in memory (single-user ad-hoc analysis).

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Backend is minimal but REAL on the one core path; frontend is visually complete with clearly-labelled NON-FUNCTIONAL stubs for everything coming later.

### Phase 1 — Upload → Ask → Answer + Auto-Chart (the wow win)

- **Goal:** A user opens the web app, uploads a CSV or `.xlsx` file, sees its detected schema, types a plain-language question in a chat, and gets back a correct plain-language answer plus an auto-chosen inline chart — with the privacy boundary enforced (only schema + aggregates reach Gemini). Minimal-but-real conversation context: the last few turns are passed so a simple follow-up works.
- **Independent slices (parallel build units):**
  - `backend-data-layer` (backend) — SQLite tables + alembic migration for `Dataset`, `Conversation`, `Message`; local file storage under `./data/uploads/`; the **aggregation engine** (load CSV/Excel via pandas, infer schema, run a planned aggregation, return a small result table) — this module is where the privacy boundary physically lives. **deps: none.**
  - `backend-agent-graph` (backend) — the LangGraph nodes (`profile_dataset` is owned by the data layer at upload time; the chat graph is `plan_aggregation` → `run_local_aggregation` → `compose_answer_and_pick_chart` → `finalize`, plus `handle_error`), the AgentState, edges, runner, and the two prompt files (`plan_aggregation.md`, `compose_answer.md`). Calls the aggregation engine via a stable function signature defined in [agent.md](agent.md). **deps: backend-data-layer (uses its aggregation function + models) — serialize after it.**
  - `backend-api` (backend) — the FastAPI routers: `POST /datasets` (multipart upload → dataset id + schema), `POST /chat` (dataset id + question + history → answer + optional chart spec), `GET /datasets/{id}` and `GET /conversations/{id}`. Wires upload→engine and chat→runner. **deps: backend-data-layer + backend-agent-graph — serialize after both.**
  - `frontend-chat-ui` (frontend) — the full chat UI: upload dropzone, message thread, input box, inline chart rendering (Recharts), and the labelled NON-FUNCTIONAL stubs (live DB connect, deeper follow-up memory, auto-insights, chart-type toggle). Builds against the API contract in [api.md](api.md). **deps: none** (builds in parallel against the spec'd contract).
- **Key surfaces / files:**
  - `backend-data-layer`: `src/db/models.py` (add `Dataset`, `Conversation`, `Message`), `alembic/versions/0002_datachat.py`, `src/data/storage.py`, `src/data/aggregation.py`, `src/data/schema.py`, `tests/unit/test_aggregation.py`, `tests/unit/test_schema.py`.
  - `backend-agent-graph`: `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/runner.py`, `src/prompts/plan_aggregation.md`, `src/prompts/compose_answer.md`, `tests/integration/test_chat_graph.py` (privacy-boundary assertion + real-Gemini end-to-end).
  - `backend-api`: `src/api/datasets.py`, `src/api/chat.py`, `src/api/__init__.py` (register routers), `src/domain/dataset.py`, `src/domain/chat.py`, `tests/integration/test_api.py`.
  - `frontend-chat-ui`: `frontend/src/app/page.tsx`, `frontend/src/components/*`, `frontend/package.json` (add `recharts`).
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` — runs migrations against the production SQLite DB and the full test suite, including `tests/integration/test_chat_graph.py` which hits the **real Gemini API** via `AGENT_GEMINI_API_KEY` from `.env` and asserts that the exact LLM-bound payload contains schema + aggregate rows but **no raw data row**. The integration test uses a fixture dataset large enough (≥ 500 rows, ≥ 12 distinct group keys) that a sampled answer and a full-data answer differ, so the gate proves the aggregation ran over the full file.
- **How the user tests it (handoff seed):**
  1. Ensure `.env` has `AGENT_GEMINI_API_KEY` and `PORT=8001`.
  2. `cd frontend && pnpm install && pnpm build` then from repo root `uv run uvicorn api:app --port 8001` (or the documented run command).
  3. Open `http://localhost:8001/app/`.
  4. Drag a CSV or `.xlsx` file (e.g. a sales export) onto the upload area → expect to see the detected columns + types + row count appear.
  5. Type "what are total sales by region?" → expect a plain-language answer and a **bar chart** rendered inline below it.
  6. Type "show that as a trend over time" / "break it down by month" → expect a follow-up answer using the prior context and a **line chart**.
  7. **Labelled stubs (must read as "coming soon", not broken):** a "Connect a live database" button, a "Deep memory" indicator, an "Auto-insights" panel, and a chart-type toggle — all visibly disabled/badged "Coming soon".

### Phase 2 — Conversation Memory + Follow-up Reasoning

- **Goal:** Turn the minimal Phase-1 context into real conversation memory — the agent reliably resolves references ("that", "those regions", "the same but for last year") across multiple turns, summarizes long histories to stay cheap, and persists conversations so a reload restores the thread. Wires the "Deep memory" stub into a real feature.
- **Independent slices (parallel build units):**
  - `backend-memory` (backend) — history summarization / sliding-window in the graph, conversation-aware `plan_aggregation`, persistence of full threads. **deps: none** (extends Phase-1 graph + data layer, owned by the same surfaces).
  - `frontend-memory` (frontend) — thread persistence/restore on reload, a real "memory depth" indicator replacing the stub, conversation list. **deps: none.**
- **Key surfaces / files:** `src/graph/nodes.py`, `src/graph/state.py`, `src/prompts/plan_aggregation.md`, `src/data/storage.py`; `frontend/src/components/*`; `tests/integration/test_followups.py`.
- **Gate command:** `uv run pytest tests/integration/test_followups.py -q` — a multi-turn scripted conversation against the **real Gemini API** asserting that turn 3 correctly resolves a reference to turn 1's result.
- **How the user tests it (handoff seed):** Reload the page mid-conversation and confirm the thread restores; ask a 3-turn chain of follow-ups referencing earlier answers and confirm each resolves correctly; the "Deep memory" badge now reflects real state.

### Phase 3 — Auto-Insights

- **Goal:** When a dataset is uploaded, the agent proactively surfaces a few notable findings (top categories, an outlier, a trend) computed locally — wiring the "Auto-insights" stub into a real panel. Privacy boundary unchanged: insights are computed locally; only aggregates reach the LLM for phrasing.
- **Independent slices (parallel build units):**
  - `backend-insights` (backend) — a local insight-detection pass (rank, outlier, trend over the aggregations) + an LLM phrasing node. **deps: none.**
  - `frontend-insights` (frontend) — the insights panel replacing the stub. **deps: none.**
- **Key surfaces / files:** `src/data/insights.py`, `src/graph/nodes.py`, `src/api/datasets.py`; `frontend/src/components/*`; `tests/integration/test_insights.py`.
- **Gate command:** `uv run pytest tests/integration/test_insights.py -q` — asserts insights are generated from a fixture dataset and contain no raw rows in any LLM payload.
- **How the user tests it (handoff seed):** Upload a dataset → confirm an "Insights" panel populates with 2–4 real findings; verify they are grounded in the data.

### Phase 4 — Live Database Connection

- **Goal:** Add a second analysis *source* — connect to a live Postgres/MySQL database (read-only) and ask the same plain-language questions against a table/view. Aggregations run **in the database** (SQL `GROUP BY`), keeping raw rows in the DB; only schema + aggregate results reach the LLM. Wires the "Connect a live database" stub into a real connector. **Note:** the app's own metadata store stays SQLite; this is a new analysis source, not a swap.
- **Independent slices (parallel build units):**
  - `backend-db-source` (backend) — a read-only DB connector, schema introspection, SQL-aggregation execution behind the same aggregation interface. **deps: none.**
  - `frontend-db-connect` (frontend) — the connection form replacing the stub + source switcher. **deps: none.**
- **Key surfaces / files:** `src/data/sources/` (file source vs db source behind one interface), `src/api/sources.py`; `frontend/src/components/*`; `tests/integration/test_db_source.py`.
- **Gate command:** `uv run pytest tests/integration/test_db_source.py -q` — against a real test Postgres + real Gemini, asserts a group-by question returns a correct answer and no raw rows leave the DB layer.
- **How the user tests it (handoff seed):** Click "Connect a live database", enter a read-only connection string, pick a table, ask a question, confirm the answer + chart match a known SQL result.

### Phase 5 — Agentic Stack Upgrade + Resilience

- **Goal:** Upgrade the agent per [agent.md](agent.md) beyond the base pipeline — add a reflection pass on the aggregation plan (validate the plan against the actual schema before executing, repair on mismatch), retries/timeouts on the Gemini calls, and graceful degradation (answer without a chart if charting fails). Harden all external calls.
- **Independent slices (parallel build units):**
  - `backend-resilience` (backend) — plan-validation/reflection node, retry/backoff + timeout wrappers around LLM calls, degraded paths. **deps: none.**
- **Key surfaces / files:** `src/graph/nodes.py`, `src/graph/edges.py`, `src/llm/client.py`, `tests/integration/test_resilience.py`.
- **Gate command:** `uv run pytest tests/integration/test_resilience.py -q` — exercises a malformed-plan path (auto-repaired) and a simulated LLM failure (degraded answer, no crash) against the real API where possible.
- **How the user tests it (handoff seed):** Ask an ambiguous/typo'd question referencing a non-existent column → confirm the agent recovers with a sensible answer instead of erroring.

### Phase 6 — Complete Agentic System + Polish

- **Goal:** All capabilities in this roadmap are real with no stubs on any active path; the running graph matches [agent.md](agent.md); README is verified end-to-end from a clean clone.
- **Independent slices (parallel build units):**
  - `backend-complete` (backend) — close any remaining gaps, full end-to-end run across both sources. **deps: none.**
  - `frontend-polish` (frontend) — remove all "coming soon" badges, final UX polish. **deps: none.**
- **Key surfaces / files:** across `src/`, `frontend/`, `README.md`, `tests/`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` — full suite green against real Gemini + (where configured) a real DB source.
- **How the user tests it (handoff seed):** Run the full flow from a clean clone following only the README; confirm every previously-stubbed surface is now functional.
