# Roadmap

## What This Agent Does

A local web application that lets a single user upload CSV or Excel files and ask questions about them — either by selecting a preset analysis type or typing a free-text natural language question. Preset analyses (summary statistics, trend over time, top/bottom N rows, and column correlation) run entirely in pandas with no LLM calls. Free-text questions are answered by Gemini, which generates pandas code that the backend executes in a sandboxed namespace and returns results as a plain-English summary, an interactive Plotly chart, and a structured table. All data stays on the machine; nothing is sent to external services except the question text for NL queries.

## Who Uses It

A single local user — a data analyst, researcher, or developer who wants fast, interactive insight into tabular data files without writing code or leaving the browser. They upload a file, pick an analysis or ask a question, and get a visual answer immediately.

## Core Problem Being Solved

Exploring a new CSV or Excel file today requires writing ad-hoc pandas scripts or opening a spreadsheet tool. This agent replaces that friction: the user drops a file, picks a question type, and gets a rendered chart and plain-English summary in seconds — with no code, no installation beyond the app itself, and no data leaving the machine.

## Success Criteria

- [ ] A user can upload a CSV or Excel file (up to 50 MB) and receive a confirmation with row count, column count, and column names within 3 seconds.
- [ ] All four preset analyses (summary stats, trend over time, top/bottom N, correlation) run and return a summary string, a Plotly chart JSON, and/or a data table without calling any external API.
- [ ] A free-text question submitted to the NL query path calls Gemini exactly once, returns a result in under 30 seconds, and the result is rendered as a plain-English summary (plus a chart and/or table where applicable).
- [ ] Upload history persists across browser refreshes (stored in SQLite); previously uploaded files can be re-selected without re-uploading.
- [ ] No uploaded file data is transmitted to any external network endpoint — confirmed by reviewing all outbound calls in the codebase.

## What This Agent Does NOT Do (Out of Scope)

- Multi-user access or authentication of any kind.
- Uploading data to external cloud storage or passing file contents to any external API.
- Scheduled or automated analysis runs — all analysis is on-demand.
- Exporting results to PDF, Excel, or any format other than what the browser renders.
- Editing, transforming, or writing back to uploaded files.
- Joins or merges across multiple uploaded files in a single analysis.
- Streaming or real-time data sources (only static file uploads).
- LLM calls for preset analyses — presets always run in pandas.

## Key Constraints

- Data locality: uploaded file bytes never leave the machine.
- LLM calls only for free-text NL queries; presets are pure pandas.
- Single user, no authentication required.
- Max upload size: 50 MB per file.
- Accepted formats: CSV, Excel (.xlsx, .xls).
- Gemini API key required only for Phase 3+ NL query capability; Phases 1–2 work without it.

---

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** It must work perfectly the first time the user tests it — zero rough edges on the tested path. Backend is minimal but REAL on the tested path. Frontend is visually complete: real UI for the upload + summary stats path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later.

---

### Phase 1 — First Delight: Upload + Summary Stats + Chart

**Goal:** The user can drag-and-drop or pick a CSV/Excel file, see a confirmation (filename, row count, column count, column list), select "Summary Statistics" (the only real preset in Phase 1), click Run, and see a plain-English summary card plus an interactive Plotly distribution chart rendered in the browser. All other presets show a "Coming in Phase 2" label. Free-text NL query shows a "Coming in Phase 3" label. The LangGraph graph is fully wired (all nodes present), with `run_nl_query` and all non-summary-stats preset branches stubbed but present.

**Independent slices (parallel build units):**

- `backend` — database migration (uploads + analyses tables), file upload endpoint, summary stats analysis endpoint + LangGraph graph wiring (all nodes, summary stats real, others stubbed), analysis runner. **deps: none**
- `frontend` — full UI: sidebar with upload history, upload panel (drag-and-drop + file picker), analysis type dropdown (Summary Stats real; others labelled "Coming in Phase 2"; NL query labelled "Coming in Phase 3"), results panel (summary card + Plotly chart rendered from JSON + table), Run button. **deps: none**

**Key surfaces / files:**

- `backend`: `alembic/versions/0002_data_analysis.py`, `src/db/models.py` (UploadRow + AnalysisRow added), `src/api/uploads.py`, `src/api/analyses.py`, `src/graph/state.py` (DataAnalysisState), `src/graph/nodes.py` (all analysis nodes), `src/graph/edges.py` (route_analysis edge), `src/graph/agent.py` (rebuilt graph), `src/graph/runner.py` (run_analysis function), `src/domain/analysis.py` (request/response Pydantic models), `tests/phase1/test_upload.py`, `tests/phase1/test_summary_stats.py`
- `frontend`: `frontend/src/app/page.tsx` (full layout), `frontend/src/components/UploadPanel.tsx`, `frontend/src/components/AnalysisPanel.tsx`, `frontend/src/components/ResultsPanel.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/lib/api.ts`

**Gate command:**
```
uv run alembic upgrade head && uv run pytest tests/phase1/ -q
```

**How the user tests it:**
1. Run: `cd frontend && pnpm build && cd .. && uv run python -m src`
2. Open `http://localhost:8001/app/` in the browser.
3. Drag a CSV file (any CSV with numeric columns) onto the upload zone or use the file picker.
4. The sidebar updates with the filename, row count, and column count. The analysis panel becomes active.
5. The analysis type dropdown shows "Summary Statistics" (active), "Trend Over Time — Coming in Phase 2", "Top / Bottom N — Coming in Phase 2", "Correlation — Coming in Phase 2", "Ask a Question — Coming in Phase 3".
6. Click "Run Analysis". A summary card appears (mean, median, min, max per numeric column) and a Plotly bar/distribution chart renders client-side from the returned JSON. The data table shows the summary rows.
7. Real on the tested path: file upload, summary stats computation (pandas, no LLM), chart JSON, table. Stubs: all other presets, NL query (clearly labelled in the UI, not broken-looking).

---

### Phase 2 — All Presets: Trend, Top/Bottom N, Correlation

**Goal:** All four preset analysis types are fully functional. The user can pick any preset from the dropdown, fill in the dynamic parameter form (date column + value column for trend; column + N for top/bottom; column A + column B for correlation), click Run, and get the appropriate chart and summary.

**Independent slices (parallel build units):**

- `backend` — implement real pandas logic in the three stub nodes (`trend_over_time`, `top_bottom_n`, `correlation`); add/update tests. **deps: none**
- `frontend` — make Trend, Top/Bottom N, and Correlation options active in the dropdown; add dynamic parameter forms for each preset type (column selectors rendered from the upload's column list); remove "Coming in Phase 2" labels for these three. **deps: none**

**Key surfaces / files:**

- `backend`: `src/graph/nodes.py` (replace stubs with real pandas logic for trend, top_bottom_n, correlation), `tests/phase2/test_trend.py`, `tests/phase2/test_top_bottom.py`, `tests/phase2/test_correlation.py`
- `frontend`: `frontend/src/components/AnalysisPanel.tsx` (dynamic param forms per preset; activate three new presets), `frontend/src/components/ResultsPanel.tsx` (scatter chart for correlation, line chart for trend)

**Gate command:**
```
uv run pytest tests/phase2/ -q
```

**How the user tests it:**
1. Server already running from Phase 1 (or restart with the same command).
2. Upload a CSV with a date column and multiple numeric columns.
3. Select "Trend Over Time", choose the date column and a value column, click Run — a line chart appears.
4. Select "Top / Bottom N", choose a column and N=5, click Run — a ranked table and bar chart appear.
5. Select "Correlation", choose two numeric columns, click Run — a scatter plot with Pearson r in the summary appears.
6. All four presets now functional. "Coming in Phase 3" label still shown for NL query.

---

### Phase 3 — Free-Text NL Query via Gemini

**Goal:** The user can type any natural language question about the uploaded data. Gemini generates pandas code; the backend executes it in a sandboxed namespace with the DataFrame in scope and returns the result as a plain-English summary, optional chart, and optional table. The "Ask a Question" path becomes fully functional.

**Independent slices (parallel build units):**

- `backend` — implement `run_nl_query` node: build prompt with DataFrame schema + sample rows, call Gemini, extract and execute generated pandas code in a sandboxed namespace, format result, return analysis output. Add safety guardrails (code execution timeout, forbidden module list). Add tests using real Gemini key. **deps: none**
- `frontend` — activate the "Ask a Question" preset in the dropdown; replace "Coming in Phase 3" label with a real free-text input box; show a loading indicator (NL queries take longer than presets). **deps: none**

**Key surfaces / files:**

- `backend`: `src/graph/nodes.py` (`run_nl_query` real implementation), `src/graph/state.py` (no changes needed), `src/prompts/nl_query.md` (Gemini system prompt), `tests/phase3/test_nl_query.py` (real Gemini key required)
- `frontend`: `frontend/src/components/AnalysisPanel.tsx` (NL query text input, loading state for longer queries), `frontend/src/components/ResultsPanel.tsx` (handles NL query result shape)

**Gate command:**
```
uv run pytest tests/phase3/ -q
```

(Requires `AGENT_GEMINI_API_KEY` set in `.env`. The gate calls Gemini with a real question against a real CSV fixture of at least 500 rows, asserting the result shape and that the answer differs from a 10-row sample answer.)

**How the user tests it:**
1. Ensure `AGENT_GEMINI_API_KEY` is set in `.env`.
2. Restart server; open `http://localhost:8001/app/`.
3. Upload a CSV; select "Ask a Question"; type "What is the average sales by region?" (or similar for the uploaded data).
4. Click Run. A loading indicator shows. Within 30 seconds, a plain-English answer appears, with an optional chart or table.
5. Confirm: file data did not leave the machine — only the question text (plus schema/sample) was sent to Gemini.

---

### Phase 4 — Agentic Stack Upgrade + Resilience

**Goal:** Harden all external calls (Gemini API, file I/O) with error handling, retries, and timeouts. Upgrade the agent graph with reflection: after `run_nl_query`, a `reflect_nl_result` node checks the generated code for obvious failures and, if found, retries once with a correction prompt. Wire guardrails on code execution output (forbidden imports, execution timeout enforced at runtime).

**Independent slices (parallel build units):**

- `backend` — add retry + timeout to `run_nl_query` (exponential backoff, max 2 retries); add `reflect_nl_result` node to graph (runs only on NL path, checks for error signals in code output, retries once with correction); add execution sandbox enforcement (importlib restriction, 10-second timeout via `signal.alarm`); add/update tests for failure modes. **deps: none**
- `frontend` — surface error states more clearly: if analysis fails, show an inline error card with the error message and a "Try Again" button rather than a blank result; add retry indicator for NL queries. **deps: none**

**Key surfaces / files:**

- `backend`: `src/graph/nodes.py` (`reflect_nl_result` node, retry logic in `run_nl_query`), `src/graph/agent.py` (updated graph with reflection edge), `src/graph/edges.py` (after_nl_query routing), `tests/phase4/test_resilience.py`
- `frontend`: `frontend/src/components/ResultsPanel.tsx` (error card + retry button)

**Gate command:**
```
uv run pytest tests/phase4/ -q
```

**How the user tests it:**
1. Temporarily set an invalid Gemini key, ask an NL question — an inline error card appears with a clear message (not a blank screen or crash).
2. Restore the valid key; ask an ambiguous question — the reflection node may retry and produce a better answer.
3. All Phase 1–3 paths still work.

---

### Phase 5 — Complete Agentic System: Drift Audit + Final Polish

**Goal:** Full drift audit (spec vs. code), no stubs on any active path, all success criteria verified end-to-end with real data, README accurate and runnable from a clean checkout.

**Independent slices (parallel build units):**

- `backend` — run qa-auditor drift check; fix any spec/code divergence; ensure all five success criteria pass against real data (a 10,000-row fixture for NL gate); final alembic migration verification. **deps: none**
- `frontend` — upload history sidebar shows timestamps and row/col counts; clicking a history entry restores the active upload without re-uploading; final visual polish pass (consistent spacing, mobile viewport). **deps: none**

**Key surfaces / files:**

- `backend`: any files flagged by drift audit; `tests/phase5/test_end_to_end.py` (full journey: upload → all 4 presets → NL query)
- `frontend`: `frontend/src/components/Sidebar.tsx` (history entries clickable with metadata), `frontend/src/app/page.tsx` (mobile layout fixes)

**Gate command:**
```
uv run pytest tests/ -q
```

**How the user tests it:**
1. Fresh clone; follow README; run `uv run alembic upgrade head && cd frontend && pnpm build && cd .. && uv run python -m src`.
2. Open `http://localhost:8001/app/`.
3. Upload a file; run all four presets; type an NL question — all paths work, no stubs visible.
4. Refresh browser; sidebar shows upload history. Click a past upload — it restores without re-uploading.
5. All success criteria from the roadmap are verifiably met.
