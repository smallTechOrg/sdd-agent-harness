# Roadmap

## What This Agent Does

A private, single-user data-analysis workbench. The user uploads CSV/Excel spreadsheets
(up to ~100MB) into a persistent library, then has long-lived conversations with an agent
that **writes and runs analysis code locally** to answer questions in plain English, backed
by charts and summary tables.

The defining constraint: **raw data rows never leave the server**. Analysis code executes
locally against the full dataset; the LLM only ever sees column schema, dtypes, basic stats,
and a tiny sample (≤5 rows). See [architecture.md](architecture.md) and [agent.md](agent.md)
for how this boundary is enforced.

## Who Uses It

One frequent, technically-comfortable power user, running the app locally on their own
machine (single trusted user). No multi-tenant auth, no sharing, no external integrations.
They repeatedly ask open-ended questions of their own spreadsheets and act on the answers,
so the production-quality bar is high.

## Core Problem Being Solved

The user repeatedly asks open-ended questions of their own spreadsheets ("which region grew
fastest last quarter, and why?"). Spreadsheet tools are too rigid; LLM chat tools either
can't run real code or require shipping the raw data to a third party. This workbench keeps
the data private, runs real pandas against the *full* file, and shows its work — the plan,
the iteration trail, and the actual code — so the user can trust and act on the answers.

## Success Criteria

- [ ] The user uploads a CSV, the system auto-profiles it (columns, dtypes, ranges, missing
      values) within a few seconds, and the profile is shown in the UI.
- [ ] The user asks a natural-language question and gets a correct plain-English answer,
      computed by pandas code that ran against the **full** uploaded file (not a sample).
- [ ] The exact generated code is visible (collapsible) alongside every answer.
- [ ] No request to the LLM ever contains a full data row beyond the declared tiny sample.
- [ ] Conversation, datasets, and run history persist across restarts (SQLite on disk).
- [ ] Every later-phase surface (library, charts, run history, cost tracker, column notes,
      multi-file joins) is present in the UI from Phase 1 as a clearly-labelled "coming soon"
      stub, never mistakable for a bug.

## What This Agent Does NOT Do (Out of Scope)

- Multi-user, authentication, sharing, or any network exposure beyond localhost.
- External integrations (BI tools, cloud warehouses, Slack, email).
- Sending raw data rows to any third party, including the LLM.
- Editing/cleaning data in place (this is read-only analysis, not a spreadsheet editor).
- Arbitrary untrusted-user code-execution sandboxing — the single user is trusted and runs
  code on their own machine (see the safety posture in [architecture.md](architecture.md)).
- Model fine-tuning or training on the user's data.

## Key Constraints

- **Privacy invariant (non-negotiable):** raw rows never reach the LLM. See
  [architecture.md](architecture.md) and [agent.md](agent.md).
- **Cost:** keep LLM spend low — default to a cheap model (`gemini-2.5-flash`) and escalate
  to a stronger model only on hard questions. See [architecture.md → Stack](architecture.md).
- **File size:** datasets up to ~100MB; profiling and execution must stream/limit memory
  sensibly and never block the event loop (run pandas off the request thread).
- **Single trusted local user:** no auth; code execution is in-process (see safety posture).

## Capabilities

See [capabilities/index.md](capabilities/index.md). Core set for v1:

1. **dataset-ingestion** — upload a spreadsheet, persist the file, auto-profile it.
2. **conversational-analysis** — plan → write pandas → run locally on full data → answer
   with visible code (the core loop; carries the privacy invariant).
3. **conversation-memory** — follow-up questions carry prior turns as context.
4. **run-history** — every question/plan/code/result/cost persisted and browsable per dataset.

Deferred (later phases, see below): interactive charts, live streaming steps, cost
tracking UI, multi-file joins / Excel multi-sheet, column notes & business rules,
clarify-vs-best-guess branching, deep iterative refinement.

---

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is minimal but
> REAL on the one core path (real Gemini call, real pandas execution — no fake data on the
> tested path). Its frontend is visually complete: real UI for the working path PLUS
> clearly-labelled NON-FUNCTIONAL stubs for everything coming later. The human tests at each
> phase boundary before the next phase starts. All gates run against the **real Gemini key
> from `.env`** and the **production SQLite DB**.

> **Assumed:** the app is served single-origin — FastAPI on port 8001 mounts the built
> Next.js static export at `/app/` (exactly as the baseline `src/api/__init__.py` already
> does). Every phase's "how the user tests it" opens `http://localhost:8001/app/` after
> `cd frontend && pnpm build` and `uv run python -m src`.

> **Assumed:** profiling and pandas execution run off the request thread (FastAPI
> `run_in_threadpool` / a worker) so a 100MB file never blocks the event loop. One agent run
> at a time per process is acceptable for a single user (see [agent.md → Concurrency](agent.md)).

### Phase 1 — Upload → profile → ask one question → answer with visible code

- **Goal:** Prove the concept end-to-end on one CSV: upload it, auto-profile it, ask one
  natural-language question, and get a correct plain-English answer computed by pandas that
  ran against the **full** file — with the generated code visible. Everything else is a
  labelled non-functional stub. The full LangGraph skeleton (all nodes/edges of the
  plan→execute→inspect→refine graph) is wired even where some nodes are minimal; the
  `plan → generate_code → execute_code → answer` core path is **REAL**. See [agent.md](agent.md).
- **Independent slices (parallel build units):**
  - `backend` (backend) — `datasets` + `runs` tables + Alembic migration; file upload to
    `uploads/` + profiling (`src/analysis/profile.py`); the full agent graph replacing the
    `transform_text` slot (`src/graph/`); the pandas execution engine
    (`src/analysis/execute.py`); prompts (`src/prompts/`); API routes `POST /datasets`,
    `GET /datasets/{id}`, `POST /ask` (`src/api/datasets.py`, `src/api/ask.py`); domain models
    (`src/domain/`); tests in `tests/phase1/`. **Deps: none.**
  - `frontend` (frontend) — the single-page workbench: upload area, profile display, ask box,
    answer panel with collapsible code + plan, and all labelled "coming soon" stubs (library,
    charts, run history, cost, column notes, multi-file). Replaces `frontend/src/app/page.tsx`.
    Talks to the API by `fetch` over the [api.md](api.md) envelopes. **Deps: none** (builds
    against the documented contract).
- **Key surfaces / files:** backend → `src/analysis/profile.py`, `src/analysis/execute.py`,
  `src/graph/{state,nodes,edges,agent,runner}.py`, `src/db/models.py`, `src/api/datasets.py`,
  `src/api/ask.py`, `src/domain/*.py`, `src/prompts/*.md`, `alembic/versions/<rev>_phase1.py`,
  `tests/phase1/*`; frontend → `frontend/src/app/page.tsx`, `frontend/src/components/*`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest`
- **How the user tests it (handoff seed):** `cd frontend && pnpm build`, then
  `uv run python -m src`, open `http://localhost:8001/app/`. Drag a CSV (e.g. a sales export,
  thousands of rows) into the upload area → within a few seconds a profile card appears
  (column names, dtypes, row count, ranges, missing-value counts). Type "what is the total
  revenue by region?" → a plain-English answer appears; expand "Show code" to see the actual
  pandas, and "Show plan" to see the agent's plan. The stub panels (Dataset Library, Charts,
  Run History, Cost, Column Notes, Multi-file) are visible and each clearly reads "Coming
  soon" — not a bug.

### Phase 2 — Persistent library, run history browser, cost tracking

- **Goal:** Turn the single-shot tool into a workbench you return to: a real dataset library
  to pick from, a browsable per-dataset run history, and a live cost panel (tokens +
  estimated dollars per query and a running daily total).
- **Independent slices (parallel build units):**
  - `backend` (backend) — `GET /datasets` list, `GET /datasets/{id}/runs` history,
    token/cost computation persisted on `runs`, `GET /cost/daily` running total; graph records
    tokens/cost per node. Owns `src/api/datasets.py` additions, `src/api/runs_history.py`,
    `src/analysis/cost.py`, `src/graph/nodes.py` cost capture, `tests/phase2/`. **Deps: none.**
  - `frontend` (frontend) — replace the Library, Run History, and Cost stubs with real wired
    components. Owns `frontend/src/components/{Library,RunHistory,CostPanel}.tsx` + `page.tsx`
    wiring. **Deps: consumes the backend slice's endpoints** (develops against [api.md](api.md)
    in parallel; integrates at the gate).
- **Key surfaces / files:** `src/api/runs_history.py`, `src/analysis/cost.py`,
  `src/graph/nodes.py` (cost capture), `frontend/src/components/{Library,RunHistory,CostPanel}.tsx`,
  `tests/phase2/*`.
- **Gate command:** `uv run pytest`
- **How the user tests it (handoff seed):** Open `http://localhost:8001/app/`. The Library
  panel now lists the datasets uploaded in Phase 1 — click one to load it. Ask a question; the
  Cost panel shows tokens + estimated $ for that query and updates the daily total. Open Run
  History for the dataset and see prior questions with their code and results.

### Phase 3 — Interactive charts + live streaming steps

- **Goal:** Answers come with auto-selected interactive charts, and while the agent works the
  user sees live step updates, a streaming answer, and an elapsed timer.
- **Independent slices (parallel build units):**
  - `backend` (backend) — the agent emits a chart spec (type + aggregated data series derived
    from the result table — chart data is server-computed, still no raw rows to the LLM);
    `POST /ask` streams step events (plan, each iteration, final answer). Owns
    `src/analysis/chart.py`, `src/api/ask.py` streaming variant, `src/graph/nodes.py` chart-spec
    emission, `tests/phase3/`. **Deps: none.**
  - `frontend` (frontend) — render interactive charts (zoom/hover/filter); consume the stream
    to show live steps + elapsed timer. Owns `frontend/src/components/{Chart,StepTrail,Timer}.tsx`
    + `page.tsx` wiring. **Deps: consumes the backend slice's stream + chart spec.**
- **Key surfaces / files:** `src/analysis/chart.py`, `src/api/ask.py`,
  `frontend/src/components/{Chart,StepTrail,Timer}.tsx`, `tests/phase3/*`.
- **Gate command:** `uv run pytest`
- **How the user tests it (handoff seed):** Ask "revenue by month" → while it runs, a step
  trail and elapsed timer update live and the answer streams in; a line/bar chart renders, and
  you can zoom, hover, and filter it.

### Phase 4 — Multi-file joins / Excel multi-sheet, column notes & business rules, clarify-vs-best-guess, deep refine

- **Goal:** Full agentic depth and multi-file power: join/compare files, multi-sheet Excel,
  auto-pick the relevant dataset, user-authored column notes/business rules the agent respects,
  clarify-or-best-guess on uncertainty, and deep iterative refinement that adapts effort to
  question difficulty.
- **Independent slices (parallel build units):**
  - `multifile` (backend) — Excel/multi-sheet loading, multi-frame execution, dataset
    auto-pick. Owns `src/analysis/load.py`, `src/analysis/execute.py` multi-frame additions, and
    the auto-pick edits to `src/graph/nodes.py`. `tests/phase4/`. **Deps: none.**
  - `notes` (backend) — `column_notes` table + migration, `src/api/notes.py`, prompt injection
    of notes. Owns `src/db/models.py` (`column_notes` only), `src/api/notes.py`,
    `src/prompts/*` notes injection. `tests/phase4/`. **Deps: none.**
  - `depth` (backend) — clarify/best-guess + deep-refine routing, difficulty router, clarify +
    refine nodes. Owns `src/graph/edges.py` and the clarify/refine edits to `src/graph/nodes.py`.
    `tests/phase4/`. **Deps: none.**
  - `frontend` (frontend) — replace the remaining stubs (Notes editor, Multi-file picker),
    render clarify prompts and the iteration trail. Owns
    `frontend/src/components/{NotesEditor,MultiFile,ClarifyPrompt}.tsx` + `page.tsx`.
    **Deps: consumes multifile/notes/depth endpoints.**

  > `multifile` and `depth` both touch `src/graph/nodes.py`. To keep them parallel, `multifile`
  > owns only the dataset-auto-pick function and `depth` owns only the clarify/refine functions
  > within that file. agent-builder serializes these two if a genuine same-region conflict
  > arises; otherwise they fan out.
- **Key surfaces / files:** `src/analysis/load.py`, `src/analysis/execute.py`,
  `src/db/models.py`, `src/api/notes.py`, `src/graph/{nodes,edges}.py`,
  `frontend/src/components/*`, `tests/phase4/*`.
- **Gate command:** `uv run pytest`
- **How the user tests it (handoff seed):** Upload a multi-sheet Excel workbook and a second
  CSV; ask a question that needs joining the two — the agent auto-picks/joins and answers. Add a
  column note ("`amt` is in cents") → re-ask → the agent respects it. Ask a vague question → the
  agent either asks a clarifying question or gives a clearly-flagged best guess. Ask a hard
  multi-step question → the iteration trail shows the agent planning, trying, inspecting, and
  refining.
