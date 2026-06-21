# UI — Interface Contract

This document is the exact, testable interface contract. Every screen is designed for all four states. Every component meets the UX bar. The executor cannot ship a bare-table proof-of-concept against this spec.

Cross-references (one fact, one place):
- `/health` response shape + `stub_mode` flag → api.md §GET /health
- Frontend port :3000, backend port :8001 → architecture.md Stack / vision.md Hard Constraints
- Stack versions → architecture.md Stack table
- `audit_log` columns → data-model.md §audit_log
- SC-N → vision.md; PN-ACn → delivery-plan.md

---

## UI Stack & Global Shell

### Frontend stack (pins)

| Concern | Library | Version pin | Why this choice (1 line) |
|---------|---------|-------------|--------------------------|
| Framework | Next.js (App Router) | 15.x | RSC + fetch; must match architecture.md |
| UI runtime | React | 19.x | Next.js 15 peer dependency |
| Styling | Tailwind CSS | 3.4.x | utility-first; no bespoke CSS files |
| Markdown table renderer | react-markdown + remark-gfm | react-markdown 9.x / remark-gfm 4.x | GFM tables not `<pre>` dumps [C-MD-RENDER] |
| Chart renderer | react-plotly.js + plotly.js | react-plotly.js 2.x / plotly.js 2.x | interactive charts; loaded SSR-safe [C-PLOTLY-SSR] |
| Data fetching | native fetch | built-in Next.js 15 | simple request/response; no streaming needed |
| Test runner (UI) | Playwright | 1.46.x | drives Live-UI gate; rendered-DOM assertions |

> **SSR guard (mandatory).** `react-plotly.js` touches `window` on import and crashes during server render. It MUST be loaded client-only:
> ```tsx
> const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });
> ```
> Any browser-only API (`window`, `localStorage`, `sessionStorage`) is read in `useEffect`, never at module/initialiser scope. Cross-ref [C-PLOTLY-SSR] and [C-SSR-BROWSER-API] in harness/rules/gotchas.md. `npm run build` passing is necessary but not sufficient — the Live-UI gate curls the running `npm run start` origin.

### Global shell regions

| Region | Position | Always present? | Holds | First phase |
|--------|----------|-----------------|-------|-------------|
| Stub-mode banner | full-width, top | yes (WHILE stub_mode=true) | verbatim stub string (see §Stub-Mode Banner) | Phase 1 |
| Top nav / brand | top bar below banner | yes | app name "Data Analyst Agent", active-screen marker | Phase 1 |
| Session sidebar | left (240px wide) | yes | session list (id/title), active highlighted, "+ New" button | Phase 1 |
| Main region | center (flex-1) | yes | the active screen (Query, Datasets, Audit) | Phase 1 |
| Error-toast region | top-right | yes | transient plain-English errors + dismiss button; max 3 stacked | Phase 1 |

```
+-------------------------------------------------------------------+
|  STUB MODE — responses are canned, not real AI output             |  <- stub-mode banner (WHILE stub)
+------------------+------------------------------------------------+
|  [Data Analyst   |  (active: Query)                [error toast]  |  <- top nav / brand
|   Agent]         |                                                |
+------------------+------------------------------------------------+
|  Sessions        |                                                |
|  > Session-3 *   |        < main region: active screen >         |  <- main region
|    Session-2     |                                                |
|    Session-1     |                                                |
|  [+ New]         |                                                |
+------------------+------------------------------------------------+
```

---

## Screens

### Screen inventory

| Screen | First phase (shell / live) | Reachable from | Specified below? |
|--------|----------------------------|----------------|------------------|
| Query | Phase 1 shell, Phase 2 live | session sidebar (default view), top nav | §Query Screen |
| Datasets | Phase 1 shell + live (upload real in P1) | top nav "Datasets" tab | §Datasets Screen |
| Audit Log | Phase 2 shell + live | top nav "Audit" tab | §Audit Log Screen |

---

### `Query Screen` (→ Phase 1 shell, Phase 2 live)

**Purpose:** let the analyst upload data (if needed) and ask natural-language questions, seeing the result as a Markdown table and Plotly chart.

**Key elements:**

| Element | Type | Source / binds to |
|---------|------|-------------------|
| Dataset selector | `<select>` multi-select | GET /datasets?session_id (api.md); populates from datasets in the current session |
| Question textarea | `<textarea rows="3">` | POST /query request `question` field (api.md §POST /query) |
| Submit button | `<button type="submit">` | triggers POST /query (api.md §POST /query) |
| Result markdown table | react-markdown + remark-gfm | `response.table_markdown` |
| Result Plotly chart | react-plotly.js (SSR-disabled) | `response.chart_spec` |
| Row-count badge | `<span>` in table header | `response.row_count` — displays exact text `{N} rows` |
| Generated SQL disclosure | `<details><summary>View SQL</summary>` | `response.sql` |
| Follow-up chips | clickable `<button>` array | `response.suggestions[]`; Phase 3 populated, Phase 1–2 show stubs |
| Thinking indicator | `animate-pulse` div | shown WHILE a query is in flight |

**Actions:**

| Action | Trigger | Effect | Backed by |
|--------|---------|--------|-----------|
| Submit question | click Submit or ⏎ in textarea | disables Submit + shows thinking indicator; calls POST /query; renders result or error | POST /query (api.md §POST /query) |
| Click follow-up chip | chip click | fills textarea with chip text AND auto-submits | UX-bar criterion #10 |
| Change dataset selection | change event on selector | updates the dataset_ids for next submission | bound to POST /query `dataset_ids` |
| Expand SQL disclosure | click `<details>` | reveals the generated SQL string below the table | no API call |

**Four states (mandatory):**

| State | What the user sees (concrete) |
|-------|-------------------------------|
| Loading | Textarea and selector are still readable; Submit button shows a spinner and is `disabled`; the result area shows an `animate-pulse` skeleton shaped like 5 table rows + a chart-area placeholder rectangle; input text is NOT cleared |
| Empty | Headline `Ask a question about your data` centered in the main region + 3 example chip buttons: `"Top 5 by revenue"`, `"Count by category"`, `"Show monthly trend"` — clicking any fills textarea + auto-submits |
| Populated | Sortable GFM table with `{N} rows` badge in header (N ≥ 1) + interactive Plotly chart (bar/line/scatter per data shape) with non-empty x-axis title, non-empty y-axis title, hover tooltips, and modebar PNG-download button + follow-up suggestion chips (≥ 0 chips, stubs in P1) + `View SQL` disclosure |
| Error | Inline red alert reading `Could not run that query — [error.message from API]` with a `Try again` button; the PRIOR result (table + chart) remains visible in the DOM; submit button re-enabled |

---

### `Datasets Screen` (→ Phase 1 shell + live)

**Purpose:** view all datasets in the current session and upload new ones.

**Key elements:**

| Element | Type | Source / binds to |
|---------|------|-------------------|
| Upload dropzone | `<input type="file">` + drag-and-drop zone | POST /datasets (api.md §POST /datasets); accepts .csv, .json, .xlsx, .parquet |
| File format badge | `<span>` | `dataset.file_format` |
| Dataset cards list | `<ul>` of cards | GET /datasets?session_id (api.md §GET /datasets) |
| Dataset name | `<h3>` in card | `dataset.name` |
| Row-count label | `<span>` | `dataset.row_count` — exact text `{N} rows` |
| Column-schema expandable | `<details>` per card | `dataset.column_schema` array; shows `name (dtype)` per column |
| Delete button (Phase 3) | `<button>` in card | DELETE /datasets/{id} (api.md §DELETE /datasets/{id}); Phase 3 only; hidden in P1–P2 |
| Upload progress bar | `<progress>` | browser upload progress event; shown during multipart POST |

**Actions:**

| Action | Trigger | Effect | Backed by |
|--------|---------|--------|-----------|
| Upload file | drag-drop or click file input + auto-submit | shows progress bar; calls POST /datasets; on success adds card to list + shows `{N} rows`; on error shows toast | POST /datasets (api.md §POST /datasets) |
| Expand schema | click `<details>` on card | reveals column list `name (dtype)` for each column | no API call |
| Delete dataset (Phase 3) | click Delete button in card | prompts confirm dialog; calls DELETE /datasets/{id}; removes card from list | DELETE /datasets/{id} (api.md §DELETE /datasets/{id}) |

**Four states (mandatory):**

| State | What the user sees (concrete) |
|-------|-------------------------------|
| Loading | `animate-pulse` skeleton showing 2 placeholder dataset cards; upload zone still visible and interactive |
| Empty | Upload dropzone with text `Drop a CSV, JSON, Excel, or Parquet file here, or click to browse` and a `Browse files` button — no blank space, no invisible zone |
| Populated | Grid of dataset cards; each card shows: `{name}` as heading, `{N} rows` badge, `{format}` badge, an expandable column list; upload zone remains visible at top |
| Error | Toast `Upload failed — [error.message]` (top-right); the upload zone remains usable; existing cards unchanged |

---

### `Audit Log Screen` (→ Phase 2)

**Purpose:** inspect every SQL execution and LLM call for the current session.

**Key elements:**

| Element | Type | Source / binds to |
|---------|------|-------------------|
| Query run selector | `<select>` | GET /sessions/{id}/history (api.md); shows past query_run_ids with their first 60 chars of `question` |
| Audit rows table | HTML `<table>` (not react-markdown) | GET /query/{id}/audit (api.md §GET /query/{id}/audit) |
| Action badge | `<span>` color-coded | `audit_row.action` — `sql` blue, `llm` purple, `error` red |
| Duration label | `<span>` | `audit_row.duration_ms` — displayed as `{ms} ms` |
| Token count | `<span>` | `audit_row.input_tokens + audit_row.output_tokens` — shown as `{N} tokens` for llm rows; `—` for sql rows |
| Payload disclosure | `<details><summary>Payload</summary>` per row | `audit_row.payload` truncated to 200 chars with `See full` expand |

**Actions:**

| Action | Trigger | Effect | Backed by |
|--------|---------|--------|-----------|
| Select query run | change on selector | loads audit rows for that query_run_id | GET /query/{id}/audit (api.md §GET /query/{id}/audit) |
| Expand payload | click `<details>` | reveals full payload text | no API call |

**Four states (mandatory):**

| State | What the user sees (concrete) |
|-------|-------------------------------|
| Loading | `animate-pulse` skeleton showing 3 placeholder rows; selector disabled during load |
| Empty | Text `No audit records yet — run a query to see SQL and LLM call logs here` centered in the main region |
| Populated | Table with ≥ 1 row; each row shows: action badge (color), payload first 60 chars, duration in ms, token count or `—`; rows ordered by `created_at` asc |
| Error | Text `Could not load audit log — Try again` with a retry button; selector remains usable |

---

## Component UX Bar

### Data tables (Query Screen)

| # | EARS criterion | Acceptance test (click sequence + asserted string) | Phase AC | Serves SC |
|---|----------------|----------------------------------------------------|----------|-----------|
| 1 | WHEN a result has N≥1 rows the table header SHALL display the exact text `{N} rows`. | Submit "top 5 by revenue" with seeded CSV → assert header element text matches `/\d+ rows/` and N≥1 | P2-AC3 | SC-CORE |
| 2 | WHEN a column header is clicked the table SHALL re-sort rows by that column (asc→desc toggle). | Click `revenue` column header twice → assert first-row cell value changes between the two clicks | P2-AC4 | SC-UX |
| 3 | IF a result exceeds 50 rows THEN the table SHALL paginate (show first 50 rows + a `Show more` button), never render all rows into the DOM at once. | Seed 200-row query → assert rendered `<tr>` count ≤ 51 (50 rows + header) + `Show more` button present | P2-AC4 | SC-UX |
| 4 | The table SHALL right-align numeric columns and render null cells as `—` (em dash), not blank. | Seed a null-containing result → assert null cell text === `—` | P2-AC4 | SC-UX |

### Charts

| # | EARS criterion | Acceptance test | Phase AC | Serves SC |
|---|----------------|-----------------|----------|-----------|
| 5 | WHEN a result is charted the chart SHALL render a title, both axis labels, and hover tooltips, and SHALL expose a PNG-download modebar button. | Submit a numeric query → assert `.modebar` exists + axis title nodes non-empty + hovering a bar shows tooltip | P2-AC3 | SC-UX |
| 6 | The chart type SHALL be chosen by data shape: line for a time-series column, bar for categorical vs numeric, scatter for two numeric columns with no categorical grouping. | Seed a date + value result → assert `trace.type === "scatter"` with `mode="lines"` | P2-AC4 | SC-UX |
| 7 | IF a result has no chartable columns THEN the chart area SHALL show the exact text `No data to chart` (never an empty Plotly canvas). | Seed a single-TEXT-column result → assert text `No data to chart` visible; assert no `.js-plotly-plot` in DOM | P2-AC4 | SC-UX |

### Query / response flow

| # | EARS criterion | Acceptance test | Phase AC | Serves SC |
|---|----------------|-----------------|----------|-----------|
| 8 | WHILE a query is in flight the Submit button SHALL be disabled and an `animate-pulse` skeleton SHALL be visible; the input text SHALL NOT clear. | Click Submit → assert `button[disabled]` + skeleton visible + textarea value === original text | P1-AC3 | SC-CORE |
| 9 | WHEN a query errors the error SHALL appear as inline text `Could not run that query — [message]` and the PRIOR result SHALL remain visible in the DOM. | Force a 500 → assert error text present AND previous table `<tr>` count unchanged | P1-AC9 | SC-FAIL |

### Follow-up chips

| # | EARS criterion | Acceptance test | Phase AC | Serves SC |
|---|----------------|-----------------|----------|-----------|
| 10 | WHEN a follow-up chip is clicked the textarea SHALL be filled with the chip text AND the query SHALL auto-submit. | Click `Break down by category` chip → assert textarea value === `"Break down by category"` AND a new result renders | P3-AC3 | SC-8 |

### Session sidebar / history

| # | EARS criterion | Acceptance test | Phase AC | Serves SC |
|---|----------------|-----------------|----------|-----------|
| 11 | The sidebar SHALL show each session's visible id/title (first 20 chars) and SHALL highlight the active session with a `bg-blue-100` background. | Assert active session list item has class `bg-blue-100` | P1-AC11 | SC-7 |
| 12 | WHEN the user clicks a session in the sidebar the main region SHALL load that session's first query string without a full page reload. | Click a second session → assert its first query string appears in main region; assert no `navigation` event fired | P2-AC7 | SC-7 |
| 13 | WHERE a new browser tab is opened the app SHALL generate a distinct session id and the session sidebar SHALL show 2 sessions after the second tab creates its session. | Open two tabs → create session in each → assert sidebar shows 2 distinct session ids | P1-AC10 | SC-7 |

### Dataset screen

| # | EARS criterion | Acceptance test | Phase AC | Serves SC |
|---|----------------|-----------------|----------|-----------|
| 15 | WHEN a file is uploaded the dataset card SHALL show `{N} rows` badge with N≥1 within 5 s of the POST /datasets 201 response. | Upload sample.csv (100 rows) → assert card badge text === `100 rows` within 5 s | P1-AC4 | SC-CORE |
| 16 | WHEN an upload is in progress a `<progress>` bar SHALL be visible in the upload zone. | Begin upload of a 5 MB file → assert `<progress>` element present and value > 0 | P1-AC4 | SC-CORE |

---

## Cross-screen interaction contracts

| # | Contract | EARS criterion OR [ASSUMPTION: value] | Acceptance test | Phase AC | Serves SC |
|---|----------|---------------------------------------|-----------------|----------|-----------|
| X1 | Pagination / page size | Table results: first 50 rows rendered; `Show more` loads the next 50 (client-side slicing of `rows`); api.md returns up to `DAA_MAX_RESULT_ROWS` (10 000) whole | Seed 200-row query → assert ≤ 51 `<tr>` elements + `Show more` button; click it → assert ≤ 101 `<tr>` | P2-AC4 | SC-UX |
| X2 | Error-toast lifecycle | WHEN an error toast shows it SHALL auto-dismiss after 6 s AND ≤ 3 toasts stack (oldest evicted if a 4th arrives) | Fire 4 errors rapidly → assert ≤ 3 toasts in DOM; wait 6 s → assert toast count == 0 | P1-AC9 | SC-FAIL |
| X3 | Initial paint (Empty CTA vs Loading) | WHILE /health is in flight the shell SHALL show an `animate-pulse` skeleton; once resolved with no prior query the main region SHALL show the Empty CTA text `Ask a question about your data` | Load app cold → assert skeleton visible then CTA text visible; assert no blank main region | P1-AC3 | SC-CORE |
| X4 | Responsive / narrow-viewport shell | [ASSUMPTION: desktop-only ≥ 1024px; viewport < 1024px shows the sidebar collapsed to a toggle hamburger button] | Set viewport to 768px → assert sidebar not visible + hamburger button present | P1-AC11 | SC-UX |

---

## Stub-Mode Banner

| Aspect | Specification |
|--------|---------------|
| Trigger | WHILE `GET /health` returns `stub_mode === true` (shape owned by api.md §GET /health) |
| Placement | full-width, top of **every** screen, above the top nav, rendered on first paint (no scroll, no flash-of-absence) |
| Copy (verbatim) | `STUB MODE — responses are canned, not real AI output` |
| Dismissable? | no — it disappears only when a real API key makes `stub_mode === false` |
| Asserted by | Stub-banner hard gate + Live-UI hard gate (harness/rules/testing.md) — banner string found in the rendered DOM of `http://localhost:3000` |

**Criterion (EARS + exact test):**

| # | EARS criterion | Acceptance test (asserted string) | Phase AC | Serves SC |
|---|----------------|-----------------------------------|----------|-----------|
| 14 | WHILE `stub_mode` is true the app SHALL display a full-width top banner reading exactly `STUB MODE — responses are canned, not real AI output` on every screen on first paint. | Start frontend with `DAA_LLM_PROVIDER=stub`; `playwright: page.goto("/"); assert page.locator("text=STUB MODE — responses are canned, not real AI output").is_visible()` | P1-AC1 | SC-STUB |

---

## Open questions / assumptions

| Item | Type | Detail |
|------|------|--------|
| Result delivery (streaming vs whole) | ASSUMPTION | whole-response delivery; POST /query returns the full result synchronously; UI shows `animate-pulse` skeleton during the wait |
| Table pagination page size | ASSUMPTION | page size 50 (client-side slicing of `rows`); api.md returns full set capped at 10 000 |
| Viewport breakpoint | ASSUMPTION | desktop-only ≥ 1024px; narrower viewports collapse sidebar to hamburger toggle |
| Error toast auto-dismiss timeout | ASSUMPTION | 6 seconds; max 3 stacked toasts (oldest evicted) |
| Session id generation (per-tab) | ASSUMPTION | `crypto.randomUUID()` in a `useEffect` (not initialiser) to avoid [C-SSR-BROWSER-API]; stored in `localStorage` read also in `useEffect` |
| Follow-up chips Phase 1–2 stub | ASSUMPTION | Phase 1–2 serve 2 hardcoded stub suggestion strings from POST /query stub response; real content from Phase 3 |
