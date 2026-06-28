# Roadmap

---

## What This Agent Does

A personal, browser-based data-analysis agent for a single power user. The user uploads a CSV (or Excel) file, then asks questions about it in plain language across a back-and-forth session. For each question the agent reasons in multiple steps — it plans a strategy, writes pandas analysis code, runs that code **server-side against the full dataset**, inspects the result, and refines if needed (bounded by a step limit). It returns a prose answer with the key numbers, an interactive chart, a results table, and the exact code it ran (shown collapsibly). Every run is saved to a per-dataset audit history.

The defining design constraint is a **hard privacy boundary**: only the file schema (column names, dtypes) and computed aggregates/results ever reach the LLM. Raw data rows never leave the server — the model generates code that executes locally, and only sees the code's output.

## Who Uses It

A single technical power user (analyst / engineer / founder) running the app locally in their browser. They are comfortable reading a chart and a number and will *act* on the answers, so they need the audit trail, the visible reasoning, and the exact code per answer to trust each result.

## Core Problem Being Solved

Replaces the slow manual loop of "open the file in pandas/Excel → write a query → re-write it → make a chart → repeat" with a conversational agent that does the planning, coding, execution, and charting — while keeping the raw data on the user's own machine and showing its work.

## Success Criteria

- [ ] User uploads a single CSV up to ~100MB and sees an auto-profile (columns, dtypes, ranges, data-quality flags) within a few seconds.
- [ ] User asks a plain-language question and watches streamed live steps (plan → write code → run → inspect → refine) with a step counter (`Step 3 of 6`).
- [ ] A typical question returns a prose answer + interactive chart + results table + collapsible exact code in ~30s.
- [ ] No raw data row is ever present in any LLM request payload (verifiable by an automated test that inspects the outbound prompt).
- [ ] Every run (question, plan, code, result, tokens, cost, timestamps) is persisted and browsable per-dataset.

## What This Agent Does NOT Do (Out of Scope)

- No persistent dataset **library** revisited across days in Phase 1 (datasets are session-scoped until Phase 2).
- No multi-file joins / folder-as-one-dataset in Phase 1 (Phase 3).
- No external integrations — no Slack, email, embed, or webhooks. Standalone web UI only.
- No multi-user accounts, auth, or sharing — single local user.
- No millions-of-rows / distributed compute optimisation — target is ~100MB CSVs answered in ~30s.
- No write-back to the source file; the agent never mutates the uploaded data.

## Key Constraints

- **Privacy boundary (hard):** raw rows never serialized into an LLM call — schema + aggregates/results only.
- **Files:** up to ~100MB CSV; ~30s answer target.
- **Cost:** stated constraint — favour a cheap/fast Gemini model (`gemini-2.5-flash`); show per-question cost + tokens + running daily total.
- **Code execution:** generated pandas code runs server-side in a restricted namespace (no filesystem/network/import escape) against the loaded DataFrame.
- **LLM:** Gemini, key in `.env` as `AGENT_GEMINI_API_KEY`, settings prefix `AGENT_`.
- **Production-ready quality:** the user acts on answers — audit trail and code-shown-per-answer are mandatory from Phase 1.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** The full LangGraph agentic skeleton (plan → generate-code → execute → inspect → refine, with the bounded step limit, clarify-first branch, and privacy boundary) is wired in Phase 1 even where individual nodes are minimal. The dataset library and multi-file joins are clearly-labelled NON-FUNCTIONAL stubs in Phase 1.

### Phase 1 — Single-file ask-and-answer with live reasoning

- **Goal:** Upload ONE CSV → agent auto-profiles it → user asks a plain-language question → user watches the agent plan / write code / run / refine live (streamed steps + step counter) → user gets a prose answer + interactive chart + results table + collapsible exact code → the run is saved to per-dataset history. Single file only. Privacy boundary enforced. Dataset library + multi-file are labelled stubs.
- **Independent slices (parallel build units):**
  - `db-schema` (backend) — SQLAlchemy models for `datasets`, `runs`, `run_steps`; rename/extend the skeleton `RunRow`. Deps: none.
  - `agent-graph` (backend) — the LangGraph plan→generate→execute→inspect→refine loop, the sandboxed code executor, the profiler, prompts, and the privacy-safe LLM payload builder. Deps: none (uses `AgentState`, imports models by name only at runtime).
  - `api` (backend) — upload endpoint, profile retrieval, the **streaming** `/ask` (SSE) endpoint that emits live steps, and the per-dataset history endpoints. Deps: `db-schema`, `agent-graph` (serializes after them at integration; owns disjoint files `src/api/*`).
  - `frontend` (frontend) — upload + profile panel, chat session with streamed step viewer + step counter, answer card (prose + chart + table + collapsible code), cost/token meter, history drawer, and labelled stubs for Library + Multi-file. Deps: none (codes against the API contract in `spec/api.md`).
- **Key surfaces / files:**
  - `db-schema`: `src/db/models.py`
  - `agent-graph`: `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/agent.py`, `src/graph/edges.py`, `src/graph/runner.py`, `src/analysis/profiler.py`, `src/analysis/executor.py`, `src/analysis/dataset_store.py`, `src/prompts/*.md`, `src/llm/payload.py`
  - `api`: `src/api/datasets.py`, `src/api/ask.py`, `src/api/history.py`, `src/api/__init__.py` (router wiring)
  - `frontend`: `frontend/src/app/page.tsx`, `frontend/src/components/*`, `frontend/tests/e2e/smoke.spec.ts`
- **Gate command:** `uv run pytest tests/phase1 -q && cd frontend && pnpm build && cd .. && (uv run python -m src &) && sleep 5 && cd frontend && npx playwright test tests/e2e/ --reporter=line`
  - `tests/phase1` runs against the **real Gemini** via `AGENT_GEMINI_API_KEY` in `.env` and the **real SQLite** DB, and MUST include `test_privacy_boundary` (asserts no raw row value appears in any captured outbound LLM payload) and `test_full_dataset_not_sampled` (gate fixture is a ≥200k-row CSV where a 1k-row sample gives an observably different aggregate than the full file — proves code runs on the full data).
- **How the user tests it (handoff seed):**
  1. Run `cd frontend && pnpm build && cd .. && uv run python -m src`, open `http://localhost:8001/app/`.
  2. Drag in a CSV (a sample sales CSV is provided at `data/samples/`). See the auto-profile panel populate (columns, dtypes, ranges, quality flags).
  3. Type a question, e.g. "What were total sales by region?" Watch the streamed steps and the `Step N of M` counter advance.
  4. Read the prose answer, hover/zoom the chart, scan the table, expand "Show code" to see the exact pandas. Check the cost/token line and daily total.
  5. Ask a follow-up ("now break that down by month") — it understands prior context.
  6. Open the history drawer — your runs are listed for this dataset.
  - **Labelled stubs (NOT bugs):** the "Dataset Library" sidebar and the "Add another file / Join files" button are greyed out and tagged "Coming in Phase 2/3".

### Phase 2 — Persistent dataset library across days

- **Goal:** Datasets and their full run history persist across server restarts and days; the user reopens a past dataset from a library sidebar and continues asking, with prior runs visible. Wires the Phase-1 "Dataset Library" stub into real functionality.
- **Independent slices (parallel build units):**
  - `library-api` (backend) — list/open/rename/delete datasets, persist uploaded files to a managed store, reload a dataset's DataFrame on demand. Deps: none.
  - `library-frontend` (frontend) — the real Library sidebar: list, search, open, rename, delete; reopen restores profile + history. Deps: none (API contract).
- **Key surfaces / files:** `library-api`: `src/api/datasets.py` (extend), `src/analysis/dataset_store.py` (extend persistence). `library-frontend`: `frontend/src/components/Library*.tsx`, `frontend/src/app/page.tsx` (wire sidebar), `frontend/tests/e2e/library.spec.ts`.
- **Gate command:** `uv run pytest tests/phase2 -q && cd frontend && pnpm build && cd .. && (uv run python -m src &) && sleep 5 && cd frontend && npx playwright test tests/e2e/library.spec.ts --reporter=line` — `tests/phase2` proves a dataset uploaded, then re-loaded in a fresh process, retains its profile + run history (real SQLite, real file store).
- **How the user tests it:** Upload a file, ask a question, restart the server, reopen the app — the Library sidebar shows yesterday's dataset; click it, see its profile + past runs, ask a new question.

### Phase 3 — Multi-file joins / folder-as-one-dataset

- **Goal:** The user adds multiple files (or points at a folder) and the agent treats them as one joinable dataset — it infers/asks join keys and runs analysis across the joined data, privacy boundary still enforced. Wires the Phase-1 "Join files" stub.
- **Independent slices (parallel build units):**
  - `join-engine` (backend) — multi-file load, join-key inference, multi-frame namespace for the executor, profiler over joined schema. Deps: none.
  - `join-api` (backend) — endpoints to add files to a dataset and configure joins. Deps: `join-engine`.
  - `join-frontend` (frontend) — multi-file upload UI, join-key configuration, joined-profile view. Deps: none (API contract).
- **Key surfaces / files:** `src/analysis/joiner.py`, `src/analysis/executor.py` (extend to multi-frame), `src/api/datasets.py` (extend), `frontend/src/components/Join*.tsx`, `frontend/tests/e2e/join.spec.ts`.
- **Gate command:** `uv run pytest tests/phase3 -q && cd frontend && pnpm build && cd .. && (uv run python -m src &) && sleep 5 && cd frontend && npx playwright test tests/e2e/join.spec.ts --reporter=line` — proves a question answered correctly across two joined CSVs, with no raw row in any LLM payload.
- **How the user tests it:** Upload two related CSVs (orders + customers), confirm the inferred join key, ask "total revenue by customer city" — get a correct cross-file answer with code shown.
