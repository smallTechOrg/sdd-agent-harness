# UI

> The single-page app for the Personal Data Analysis Agent. Next.js 15 static export, served at `http://localhost:8001/app/`. Phase 1 ships the full visual frame: real UI for upload→ask→answer, plus clearly-labelled NON-FUNCTIONAL stubs for everything deferred (a stub must never read as a bug).

---

## UI Type

Single-page web app (Next.js 15 + React 19 + Tailwind, static export). One screen with a left rail (stubbed session/dataset list in Phase 1) and a main analysis column.

## Chart library

**Chosen: Plotly (`react-plotly.js` + `plotly.js`).** It supports interactive zoom/hover/filter out of the box, renders fully client-side (compatible with a static export — no SSR needed), and consumes a JSON figure spec, which is exactly what the `select_chart` node emits. Charts are rendered with `dynamic(() => import(...), { ssr: false })` to keep them client-only in the static export.

## Views / Screens

### Screen: Analysis Workspace (the only screen)

**Purpose:** Upload a dataset, ask questions, read answers with full transparency.

**Key elements (Phase 1, REAL):**
- **Upload zone** — drag-drop/click to upload a CSV/.xlsx (`POST /datasets`). On success shows name, row count, and the sample preview. A bundled `data/sample/sales.csv` is offered as a one-click sample.
- **Question box** — plain-language input + Ask button (`POST /analyses`). Disabled until a dataset is loaded.
- **Staged progress** — while awaiting the answer, a stepper shows Planning → Writing code → Running on your data → Building chart (driven by `stage`). Non-streamed in Phase 1; a "Live streaming — coming soon" label sits beside it.
- **Answer panel** — plain-language prose + key numbers (headline figures).
- **Interactive chart** — Plotly figure from `chart_spec` (hover/zoom/filter).
- **Summary table** — the small result (`summary_table`).
- **Collapsible code panel** — "Show code" reveals the exact generated pandas/SQL (`code`).
- **Transparency panel** — "What was sent to the LLM" reveals `llm_payload` (schema + sample + prior result) — proving no bulk rows left the machine.
- **Per-question cost** — a line like `~$0.0007 · 1,240 in / 320 out tokens` from the response.

**Key elements (Phase 1, LABELLED STUBS — visible, disabled, "Coming soon"):**
- Left rail: **Sessions** list (New / Resume) — Phase 2.
- **Dataset profile** panel toggle (sample shown; full profile "coming soon") — Phase 2.
- **Follow-up suggestions** chips area (empty, labelled) — Phase 2.
- **Daily cost total** widget (shows per-question only; daily "coming soon") — Phase 3.
- **Column notes & business rules** editor (read-only placeholder) — Phase 3.
- **Export** menu (CSV / chart image / report — disabled) — Phase 4.
- **Save as dataset** action (disabled) — Phase 4.
- **Analysis library** entry (disabled) — Phase 4.
- **Connect a database** + **Join multiple files** entries (disabled) — Phase 5.

Every stub renders a tooltip/badge "Coming in a later phase" and is visibly disabled — it never errors or looks broken.

**Actions available (Phase 1):** upload a file, load the bundled sample, ask a question, expand/collapse the code panel, expand/collapse the transparency panel, interact with the chart (zoom/hover), copy the code.

## Error States

- **Upload error** — inline message on the upload zone (bad file / too large / parse error) with the `code`/`message` from the envelope.
- **Analysis failed** — the answer panel shows the error and, if the agent ran code, the attempted code + "what I tried" (flagged best-guess vs hard failure are visually distinct).
- **Loading** — the staged progress stepper; the Ask button shows a spinner and is disabled mid-run.
- **Empty states** — before upload, a friendly "Upload a dataset to begin"; before a question, the answer area shows a hint.

## Tech Stack

Next.js 15 + React 19 + Tailwind CSS (v4), static export (`pnpm build` → `frontend/out/`, mounted at `/app/`). Charts via `react-plotly.js`/`plotly.js` (client-only). API access via a small typed client `frontend/src/lib/api.ts`. E2E via Playwright (`tests/e2e/`) against the live app.
