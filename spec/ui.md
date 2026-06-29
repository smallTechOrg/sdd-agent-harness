# UI

---

## UI Type

Web dashboard — Next.js static export served by FastAPI at `http://localhost:8001/app/`. Single-page analyst workspace. Replaces the skeleton transform form (`frontend/src/app/page.tsx`).

## Views / Screens

### Screen: Analyst Workspace (single page)

**Purpose:** Upload data, ask questions, read answers with the exact SQL; later, see charts/tables/profile/cost/history.

**Layout (Phase 1 — REAL vs STUB clearly labelled):**

- **Header** — app title. REAL.
- **Upload panel** — file picker + "Upload CSV" button; on success shows the dataset name, row count, and column list. REAL (Phase 1).
- **Question panel** — text box + "Ask" button, enabled once a dataset is loaded. REAL (Phase 1).
- **Answer panel** — plain-English answer; a "best-guess" badge when `flagged`; an **"Exact SQL"** block showing the generated DuckDB query; a small result table of the aggregate `result` rows. REAL (Phase 1).
- **Datasets sidebar** — list / multi-select of datasets. STUB — visible, disabled, labelled "Coming soon".
- **Chart area** — STUB, "Coming soon" (Phase 2).
- **Summary table (rich)** — STUB, "Coming soon" (Phase 2).
- **Profile panel** — STUB, "Coming soon" (Phase 2).
- **Follow-up chips** — STUB, "Coming soon" (Phase 2).
- **Cost meter** (tokens + est. cost, session total) — STUB, "Coming soon" (Phase 3).
- **History / audit-trail browser** — STUB, "Coming soon" (Phase 3).
- **Live step stream** — STUB, "Coming soon" (Phase 3).

> Every stub renders in a disabled/greyed state with a clear "Coming soon" label so it is never mistaken for a bug.

**Actions available (Phase 1):**
- Upload a CSV.
- Type and submit a question.
- Read the answer + exact SQL + result table.

**Phase 2 wires:** chart, summary table, profile panel, follow-up chips (clicking a chip submits it as the next question).

**Phase 3 wires:** datasets sidebar (multi-select for compare/join), notes editor, cost meter + expensive-query warning modal, history browser, live SSE step stream, Excel upload.

## Error States

- **Upload error** — red banner with the message (bad file, too large, ingest failure).
- **Ask error / failed run** — the answer panel shows the failure reason and that no number could be verified (never a fabricated figure). When `flagged`, an amber "best-guess" badge appears with the answer.
- **Loading** — upload and ask buttons show a spinner/disabled state; the answer panel shows a "Working…" placeholder while the agent runs (Phase 3 replaces this with the live step stream).
- **Network error** — "is the server running?" message (as in the skeleton).

## Tech Stack

Next.js (static export) + React + Tailwind (as in the skeleton). Client-side fetch to the FastAPI endpoints. Chart rendering (Phase 2) is client-side from the backend chart spec. E2E tests use **Playwright** in `frontend/tests/e2e/` — the Phase 1 gate runs the upload→ask→answer smoke test against the real app.
