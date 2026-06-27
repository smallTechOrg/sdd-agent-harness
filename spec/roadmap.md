# Roadmap

---

## What This Agent Does

A personal, browser-based CSV data-analysis agent. The user uploads a CSV in the browser, asks questions about it in plain English, and gets plain-English answers back. All filtering, aggregation, math (and later chart rendering) happen **locally** in Python with pandas; only the user's question plus a small derived data profile — never the raw rows — is sent to a cheap cloud LLM (Gemini 2.5 Flash). It replaces opening a spreadsheet and manually writing formulas/pivot tables to answer ad-hoc questions about a file.

## Who Uses It

A single, non-technical-to-semi-technical individual analyzing their own CSV files on their own machine, on demand. They want quick answers about a dataset without writing formulas or SQL, and they care that their raw data never leaves their computer.

## Core Problem Being Solved

Answering ad-hoc questions about a CSV today means manual spreadsheet work (filters, pivots, formulas) or trusting a cloud tool with the raw data. This agent gives plain-English answers while keeping raw rows local — the privacy guarantee is the differentiator.

## Success Criteria

- [ ] User can open the web app, upload a CSV, and see its schema (columns + types) and row count.
- [ ] User can ask a plain-English question and get a correct answer whose numbers match a local pandas computation.
- [ ] The raw dataset (full DataFrame / any complete row) is provably never included in the LLM prompt — asserted by an automated test.
- [ ] The agent uses `gemini-2.5-flash` and sends only small derived artifacts, keeping cost low.
- [ ] Failures (bad CSV, unknown dataset, LLM down) surface as human-readable copy, never a crash or stack trace.

## What This Agent Does NOT Do (Out of Scope / Deferred)

- **Database connectors / live DB connections** — out of scope (intake: "mostly just CSV files"). Shown as an intentionally-excluded UI card.
- **Multi-file / joining datasets** — deferred.
- **Non-CSV spreadsheets (`.xlsx`)** — deferred; Phase 1 accepts `.csv` only.
- **Conversation memory / follow-up questions referencing prior turns** — deferred (each ask is independent in Phase 1). See [agent.md](agent.md#memory--context).
- **LLM-generated code execution** — explicitly avoided for safety; may never be added. Phase 1 is profile-grounded answering only.
- **Authentication / multi-user** — single local user only.

## Key Constraints

- **PRIVACY (dealbreaker):** raw rows never leave the machine — only the question + derived profile cross to Gemini. Enforced in code at `build_prompt` and asserted by test in every phase.
- **COST (dealbreaker):** minimize tokens (send aggregates, not rows) and use the cheap `gemini-2.5-flash` model (`AGENT_LLM_MODEL=gemini-2.5-flash`).
- **Provider:** Gemini (`AGENT_GEMINI_API_KEY`), env prefix `AGENT_`.
- **Interface:** single-origin FastAPI serving the Next.js static export at `http://localhost:8001/app/`.
- **DB:** SQLite (`data/agent.db`) — the production DB for this local tool; no PostgreSQL.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Backend is minimal but REAL on the one core path (no fake data on the tested path). Frontend is visually complete: real upload+ask UI PLUS clearly-labelled non-functional stubs for Charts and Anomalies (and an intentionally-excluded "connect a database" card), so a stub is never mistaken for a bug.

### Phase 1 — Upload a CSV, ask a question, get a grounded answer

- **Goal:** Open the web app → upload a CSV → type a plain-English question → get a correct plain-English answer computed from a LOCAL pandas profile, with raw rows provably never sent to Gemini. Charts and Anomalies appear as labelled stubs.
- **Independent slices (parallel build units):**
  - `backend-datasets` (backend) — dataset store + profiler + DB model/migration + upload/ask API routes. Deps: none. Owns the privacy boundary in code.
  - `backend-agent` (backend) — replace the LangGraph capability slot (nodes/edges/state) + the answer system prompt + runner wiring for the ask flow. Deps: **declared dependency on `backend-datasets`** for the `DataProfile`/store interface (it consumes `load_profile` and the `dataset_id` contract). Serialize after `backend-datasets` lands the profiler+store interface; the API route slice and agent slice share the runner contract.
  - `frontend-ui` (frontend) — replace `page.tsx` with the upload+ask UI, schema display, answer panel, privacy note, and the labelled Charts/Anomalies/DB stubs. Deps: none (codes against the API contract in [api.md](api.md); independent of backend build order).
- **Key surfaces / files:**
  - `backend-datasets`: `src/datasets/store.py`, `src/datasets/profiler.py`, `src/db/models.py` (+ Alembic migration adding `DatasetRow` and `runs.dataset_id`), `src/api/datasets.py`, `src/api/__init__.py` (router include), `src/domain/dataset.py`, `src/config/settings.py` (add `max_upload_mb`).
  - `backend-agent`: `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/runner.py`, `src/prompts/answer.md`, `src/llm/providers/gemini.py` (default model note — model set via env).
  - `frontend-ui`: `frontend/src/app/page.tsx` (+ small components under `frontend/src/app/`).
- **Gate command:** `uv run alembic upgrade head && AGENT_LLM_MODEL=gemini-2.5-flash uv run pytest tests/phase1 -q`
  - The suite runs against the **real Gemini API** (key from `.env`) and **SQLite** (the production DB here). It MUST include: (1) an upload → ask end-to-end test that asserts the returned answer's number matches the local pandas computation for a non-trivial question (e.g. "which <category> has the highest total <numeric>?" over a fixture with ≥200 rows and ≥5 categories, so a sampled answer and the full-data answer differ — the fixture forces the difference); (2) a **boundary assertion** that the prompt string built by `build_prompt` (and sent to Gemini) does NOT contain any full data row / the raw DataFrame, only profile fields; (3) a bad-CSV and an unknown-dataset test asserting graceful human-readable failure.
- **How the user tests it (handoff seed):** Run `python agent.py --run`. Open `http://localhost:8001/app/`. Upload a CSV (e.g. a sales file with `region` and `revenue` columns). Confirm the column list + row count appear. Type "Which region has the highest total revenue?" and click Ask. Within a few seconds a plain-English answer appears naming the correct region. The **Charts** and **Automatic patterns & anomalies** cards are visibly greyed-out with `Coming in Phase 2` / `Coming in Phase 3` badges (labelled stubs, not bugs), and a **Connect a database** card is marked `Not planned — CSV only`. The privacy note is visible.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.

### Phase 2 — Charts & visual summaries

- **Goal:** Wire the Charts stub into a real feature: the user asks for a chart (e.g. "sales by region") and sees a chart rendered in the browser, computed locally — only the derived aggregated series (never raw rows) leaves the machine. See [visual_summary.md](capabilities/visual_summary.md).
- **Independent slices (parallel build units):**
  - `backend-chart` (backend) — `POST /datasets/{id}/chart`: a chart-planning LLM call (returns a plan), local pandas execution of the plan, validated against the schema, returning a compact `chart_spec`. Deps: reuses the Phase-1 profiler/store (already landed; no new dependency).
  - `frontend-chart` (frontend) — replace the Charts stub with a real chart request input + a rendering component (e.g. a lightweight chart lib) consuming `chart_spec`. Deps: none (codes against the chart API contract).
- **Key surfaces / files:** backend: `src/api/datasets.py` (chart route), `src/graph/` (chart-plan node or a small dedicated function), `src/prompts/chart.md`. frontend: `frontend/src/app/page.tsx` Charts card → real component + a `frontend/src/app/Chart.tsx`.
- **Gate command:** `uv run alembic upgrade head && AGENT_LLM_MODEL=gemini-2.5-flash uv run pytest tests/phase2 -q`
  - Test asserts: a "total <numeric> by <category>" request returns a `chart_spec` whose series equals the local pandas groupby-sum (over a ≥200-row fixture), the plan references only real columns, and no raw row appears in the prompt or `chart_spec`.
- **How the user tests it (handoff seed):** Open `http://localhost:8001/app/`, upload a CSV, open the now-active Charts card, type "total revenue by region", and see a bar chart with one bar per region matching the data. Anomalies card remains a labelled `Coming in Phase 3` stub.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.

### Phase 3 — Automatic patterns & anomaly detection

- **Goal:** Wire the Anomalies stub into a real feature: the user clicks "Find patterns & anomalies" and gets a prioritized plain-English list of notable findings, computed locally and phrased by the LLM from derived statistics only. See [detect_anomalies.md](capabilities/detect_anomalies.md).
- **Independent slices (parallel build units):**
  - `backend-insights` (backend) — `POST /datasets/{id}/insights`: local pandas anomaly/pattern detection (outliers, null rates, skew, correlations) → one LLM call to rank/phrase the derived findings → `findings` list. Deps: reuses Phase-1 profiler/store.
  - `frontend-insights` (frontend) — replace the Anomalies stub with a real "Find patterns & anomalies" action + a findings list view. Deps: none (codes against the insights API contract).
- **Key surfaces / files:** backend: `src/api/datasets.py` (insights route), `src/datasets/anomalies.py` (local detection), `src/prompts/insights.md`. frontend: `frontend/src/app/page.tsx` Anomalies card → real component + a `frontend/src/app/Insights.tsx`.
- **Gate command:** `uv run alembic upgrade head && AGENT_LLM_MODEL=gemini-2.5-flash uv run pytest tests/phase3 -q`
  - Test asserts: a fixture with an injected extreme outlier yields a high-severity finding naming the right column; a high-null column yields a null-rate finding; the prompt contains only derived statistics (no raw rows); every returned finding maps to a supplied column/statistic (no fabrication).
- **How the user tests it (handoff seed):** Open `http://localhost:8001/app/`, upload a CSV, click "Find patterns & anomalies", and see a short ranked list of plain-English findings (outliers, missing-data columns, notable relationships). No labelled stubs remain except the intentionally-excluded `Connect a database — Not planned` card.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.
