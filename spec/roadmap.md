# Roadmap

---

## What This Agent Does

This agent is a **local-first data analyst**. A user uploads a CSV file and asks a question about it in plain English ("What were total sales by region?", "Which 5 customers spent the most?", "How many orders shipped late?"). The agent inspects the file's column schema and a small sample of rows, has an LLM translate the question into a pandas computation, runs that computation **locally over the full file** in a constrained sandbox, and returns the computed answer together with a plain-English explanation **and the exact pandas code that produced it** — so every answer is auditable. The dataset itself never leaves the machine; only the schema, a capped sample of rows, and the question are sent to the LLM.

## Who Uses It

A non-technical or semi-technical analyst, operations person, or founder who has a spreadsheet and a question, but does not want to write pandas/SQL or hand confidential data to a third-party service. They want a correct number with the working shown, fast, without learning a query language.

## Core Problem Being Solved

Answering an ad-hoc question about a CSV today means either (a) writing pandas/SQL by hand, (b) building a pivot table by trial and error, or (c) pasting the data into a hosted chatbot — which is slow, error-prone, or leaks the data. This agent removes all three: it generates and runs the computation for you, keeps the raw data local, and shows its work so you can trust the result.

## Success Criteria

- [ ] A user can upload a CSV, type a natural-language question, and receive a correct computed answer within one request, with no manual setup.
- [ ] Every answer includes the exact pandas code that produced it and a tabular/numeric result, visible in the UI.
- [ ] The full dataset is never transmitted to the LLM — only the schema, a capped row sample (≤ the configured cap), and the question. This is verifiable from the prompt payload.
- [ ] The four core analytical shapes return correct results against the real LLM: a group-by aggregation, a filter + aggregate, a sort + top-N, and a single-value aggregate (count/sum/mean).
- [ ] A malformed or non-CSV upload, and a question that cannot be answered from the columns, both fail gracefully with a clear message instead of crashing or returning a wrong number.

## What This Agent Does NOT Do (Out of Scope)

Out of scope for v1 (each is a clearly-labelled stub in the Phase-1 UI where noted, and a candidate for a later phase):

- **Charts / visualizations** — the answer is numeric/tabular text only. (Labelled stub in UI.)
- **Multiple files / joins across files** — one CSV per request.
- **Live database connections** (Postgres/MySQL/warehouse). (Labelled stub in UI.)
- **Large-file streaming / out-of-core processing** — the file must fit in memory; an enforced size/row cap rejects anything larger.
- **Conversation / follow-up memory** — each question is independent; no "and now filter that to last year".
- **Export** of results (CSV/Excel/PDF download).
- **Editing or writing back** to the dataset — read-only analysis.
- **Authentication / multi-tenant** — single local user.

## Key Constraints

These two are **non-negotiable** and the architecture is designed around them:

1. **Data stays local.** The uploaded dataset is processed on-machine. Only minimal context — the column schema and a **capped sample of rows** (default 15, hard cap 20, configurable via `AGENT_SAMPLE_ROWS`) — plus the user's question may be sent to the LLM. The **full** dataset is **never** sent to the LLM or any third party. The actual computation runs locally over the full file.
2. **Show its work.** Every answer exposes the actual pandas snippet the agent generated and executed, surfaced in the UI alongside the answer, so the result is auditable.

Additional constraints:

- **Sandboxed execution.** The LLM-generated code runs in a restricted namespace (no imports, no file/network/`os`/`open` access, no dunder traversal), with `df` (the full DataFrame) and a curated set of pandas/builtins as the only available names, under a wall-clock timeout and a row/size cap. See [`architecture.md` → Sandbox Security Model](architecture.md#sandbox-security-model).
- **Real-LLM gates.** All tests and gates run against the **real Gemini API** using `AGENT_GEMINI_API_KEY` from `.env`. No stubbed-LLM run counts as a passing gate.
- **File limits.** Upload capped at 5 MB and 200,000 rows by default (`AGENT_MAX_UPLOAD_BYTES`, `AGENT_MAX_ROWS`); larger files are rejected with a clear message.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Backend is minimal but REAL on the one core path (no fake data on the tested path). Frontend is visually complete: real UI for the working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later.

### Phase 1 — Upload a CSV, ask a question, get an auditable answer

- **Goal:** A user opens the app, uploads a CSV, types a natural-language question, and gets back a computed answer, a plain-English explanation, the generated pandas code, and the result table — all on the real Gemini API, with the full data processed locally. This is the complete core loop.
- **Independent slices (parallel build units):**
  - `backend-analyst` (backend) — the entire backend vertical: extend the domain/API/state/prompts, replace the `transform_text` node with the analyst nodes (`profile_csv` → `generate_code` → `execute_code` → `explain_result`), build the **local sandbox executor**, and the CSV profiler. Deps: none.
  - `backend-tests` (backend) — Phase-1 test suite against real Gemini covering the four analytical shapes plus the two failure guards. Deps: declared dependency on `backend-analyst` (imports its modules); **serialize after `backend-analyst`**.
  - `frontend-ui` (frontend) — replace `page.tsx` with the analyst UI: CSV upload, question input, answer + explanation display, a "Show its work" panel (generated code + result table), and clearly-labelled non-functional stubs for deferred features. Deps: none (codes against the documented API shape in [`api.md`](api.md); builds in parallel with backend).
- **Key surfaces / files:**
  - `backend-analyst` writes: `src/domain/run.py`, `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/runner.py`, `src/api/runs.py`, `src/db/models.py` (add `question`, `generated_code`, `result_table`, `answer`, `explanation` columns to `RunRow`), `alembic/versions/0002_analyst.py` (new migration for those columns), `src/analysis/profiler.py` (new), `src/analysis/sandbox.py` (new), `src/prompts/generate_code.md` (new), `src/prompts/explain_result.md` (new), `src/config/settings.py` (add `sample_rows`, `max_upload_bytes`, `max_rows`, `exec_timeout`, `max_result_rows`), `pyproject.toml` (add `pandas`).
  - `backend-tests` writes: `tests/integration/test_analyst.py` (new), `tests/fixtures/*.csv` (new). It also updates the now-obsolete transform tests `tests/integration/test_pipeline.py` and `tests/unit/test_api.py` to the analyst contract.
  - `frontend-ui` writes: `frontend/src/app/page.tsx` only.
  - Disjoint: backend slices touch only `src/` + `tests/`; frontend touches only `frontend/`. No shared file between backend and frontend.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/integration/test_analyst.py tests/unit/test_api.py -q` (runs against the real Gemini API via `AGENT_GEMINI_API_KEY` in `.env`; SQLite is the production driver for this single-user local tool).
- **How the user tests it (handoff seed):**
  1. Build the frontend and start the server: `cd frontend && pnpm build` then (from repo root) `uv run python -m src`.
  2. Open **http://localhost:8001/app/** (note the port, `/app/`, and trailing slash).
  3. Upload the sample file `tests/fixtures/sales.csv` (shipped with the build).
  4. Type: **"What were total sales by region, highest first?"** and submit.
  5. Expected (REAL): an answer naming the regions with their summed sales in descending order, a one-paragraph plain-English explanation, a "Show its work" panel showing the generated pandas (a `groupby('region')['sales'].sum().sort_values(...)`-style snippet), and a result table of region → total.
  6. Also try a bad input: upload a `.txt` or a malformed file → expect a clear "couldn't read that as a CSV" message, not a crash.
  7. **Labelled stubs (NOT bugs):** a greyed-out "Charts (coming soon)" area, a disabled "Connect a database (coming soon)" control, and a disabled "Export results (coming soon)" button. These are intentionally non-functional placeholders showing the roadmap.

### Phase 2 — SQL query mode alongside pandas

- **Goal:** Add SQL as an alternative analysis mode. Users toggle between Pandas and SQL modes before asking a question. In SQL mode, the agent loads the CSV into an in-memory SQLite table, generates SQL (not pandas) to answer the question, runs it locally, and shows the generated SQL code in "Show its work" — mirroring all the pandas path's capabilities (group-by, filter+aggregate, top-N, scalar, error handling). Both modes keep data local (only schema + sample + question to Gemini; full dataset computed locally), always expose generated code, and handle edge cases (malformed CSV, unanswerable questions).
- **Independent slices (parallel build units):**
  - `backend-sql` (backend) — add SQL generation and execution paths in the analyst node. Extend `generate_code` to branch on a `mode` field (pandas vs SQL); add SQL-specific prompts (`generate_sql.md`), a SQLite table builder, and a local SQL executor (mirroring the pandas sandbox's restrictions: sandboxed execution, timeout, result-size caps). Deps: none.
  - `backend-tests-sql` (backend) — integration tests for SQL mode, mirroring all the Phase-1 pandas tests (group-by, filter+aggregate, top-N, scalar, malformed CSV, unanswerable question) against real Gemini. Deps: declared dependency on `backend-sql`; serialize after it.
  - `frontend-mode-toggle` (frontend) — add a mode toggle control (Pandas / SQL) above the question input; wire it to the request payload (add `mode` field). Deps: none.
- **Key surfaces / files:**
  - `backend-sql` writes: `src/graph/nodes.py` (extend `generate_code` + `execute_code` to handle SQL), `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/state.py` (add `mode: str` field), `src/analysis/sql_executor.py` (new), `src/prompts/generate_sql.md` (new), `src/domain/run.py` (extend for SQL).
  - `backend-tests-sql` writes: `tests/integration/test_analyst_sql.py` (new), `tests/fixtures/*.csv` (new or reused).
  - `frontend-mode-toggle` writes: `frontend/src/app/page.tsx` (add mode toggle control above question input).
  - Disjoint: backend slices touch only `src/` + `tests/`; frontend touches only `frontend/`. No shared file between backend and frontend beyond the API contract.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/integration/test_analyst.py tests/integration/test_analyst_sql.py tests/unit/test_api.py -q` (runs against the real Gemini API via `AGENT_GEMINI_API_KEY` in `.env`; SQLite is the production driver).
- **How the user tests it (handoff seed):**
  1. Build and start the app as in Phase 1.
  2. Open **http://localhost:8001/app/** and upload `tests/fixtures/sales.csv`.
  3. **Test Pandas mode (existing):** toggle to Pandas (default), type **"What were total sales by region, highest first?"**, submit → expect the same pandas answer, code, and result table as Phase 1.
  4. **Test SQL mode (new):** toggle to SQL, type **"What were total sales by region, highest first?"**, submit → expect a correct answer (same numbers as pandas), a one-paragraph plain-English explanation, a "Show its work" panel showing the generated **SQL** (a `SELECT ... GROUP BY ... ORDER BY ...` snippet), and a result table. The SQL is sandboxed (no multi-statement, no mutations, no file access) and executed against a local in-memory SQLite table built from the CSV.
  5. **Test SQL edge cases:** upload a CSV with a column that does not apply (e.g., "gender" in a sales table), toggle to SQL, ask **"What was the average gender?"** → expect a clear "I can't compute that" error (not a wrong result).
  6. **Labelled stubs (unchanged):** greyed-out "Charts (coming soon)", disabled "Connect a database (coming soon)", disabled "Export results (coming soon)". These remain as Phase 1.

### Phase 3 — Robustness, retry, and richer result handling

- **Goal:** Harden the core loop for both pandas and SQL modes: when the generated code errors or returns nothing usable, the agent shows a clear, specific message (and optionally retries once with the error fed back), large result tables are paginated/capped sensibly, and the four analytical shapes plus edge cases (empty result, all-null column, division-by-zero) are covered end-to-end for both modes.
- **Independent slices (parallel build units):**
  - `backend-resilience` (backend) — one bounded retry of `generate_code` when `execute_code` raises (feeding the error back to the LLM), result-size capping/truncation with a "truncated" flag, and clearer sandbox error categorization for both pandas and SQL paths. Deps: none.
  - `backend-edgetests` (backend) — edge-case integration tests (empty result, all-null, divide-by-zero, question unanswerable from columns) for both pandas and SQL modes against real Gemini. Deps: declared dependency on `backend-resilience`; serialize after it.
  - `frontend-polish` (frontend) — render the "truncated" flag, the retry/error states, and an empty-result state cleanly in the UI. Deps: none.
- **Key surfaces / files:**
  - `backend-resilience` writes: `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/analysis/sandbox.py`, `src/analysis/sql_executor.py`, `src/domain/run.py`.
  - `backend-edgetests` writes: `tests/integration/test_analyst_edges.py` (new), `tests/integration/test_analyst_sql_edges.py` (new), `tests/fixtures/*.csv` (new).
  - `frontend-polish` writes: `frontend/src/app/page.tsx`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/integration -q` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** Start the app as in Phase 2, open http://localhost:8001/app/, upload `tests/fixtures/sales.csv`. Test pandas mode: ask a deliberately impossible question ("What is the average customer satisfaction score?" when no such column exists) → expect a clear error message. Test SQL mode: ask the same impossible question → expect the same clarity. Then ask a filter that matches no rows in each mode ("total sales where region = 'Atlantis'") → expect a clean "no matching rows" answer in both. The code panel shows what was attempted in each mode.

### Phase 4 — Charts (wire the first deferred stub)

- **Goal:** Turn the "Charts (coming soon)" stub into a real, optional chart for results that are naturally chartable (a group-by series), rendered locally from the computed result table — no new data leaves the machine. Both pandas and SQL modes support charts.
- **Independent slices (parallel build units):**
  - `backend-chartspec` (backend) — emit a small, declarative chart spec (type + x/y from the result table) when the result is chartable, agnostic to whether the result came from pandas or SQL. Deps: none.
  - `frontend-charts` (frontend) — render the chart spec with a local chart library; remove the stub label. Deps: declared dependency on `backend-chartspec`'s response field; serialize the chart-render test after it, but the component scaffold can start in parallel.
- **Key surfaces / files:**
  - `backend-chartspec` writes: `src/graph/nodes.py`, `src/domain/run.py`, `tests/integration/test_chartspec.py` (new).
  - `frontend-charts` writes: `frontend/src/app/page.tsx`, `frontend/package.json`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/integration -q` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** Open http://localhost:8001/app/, upload `tests/fixtures/sales.csv`. Test pandas mode: ask "total sales by region" in Pandas mode → expect the answer/code/table PLUS a bar chart of region totals. Test SQL mode: ask the same question in SQL mode → expect the same chart (derived from the SQL result). The "Charts (coming soon)" stub is now a real chart.

> Further deferred work (each its own future phase, currently labelled stubs or out-of-scope): live database connections, multi-file joins, large-file streaming, conversation/follow-up memory, result export.
