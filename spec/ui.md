# UI

## UI Type

Single-page web workbench (Next.js 15 static export + React 19 + Tailwind), served at
`http://localhost:8001/app/`. One screen with several panels. Replaces the baseline
`frontend/src/app/page.tsx` transform form.

**Stub discipline:** every later-phase surface is present from Phase 1 as a clearly-labelled
NON-FUNCTIONAL stub — a muted panel with a "Coming soon" badge and a one-line description of
what it will do. A stub must read as planned-and-pending, never as a broken feature. Real,
on-the-path surfaces look and behave fully; stubs are visually distinct (dimmed, badge).

## Views / Screens

### Screen: Workbench (single page)

**Purpose:** upload data, ask questions, read answers with full transparency.

**Layout:** left sidebar (Library) + main column (active dataset + chat) + right rail
(transparency: plan, code, cost). On small screens these stack.

**Key elements — REAL in Phase 1:**

- **Upload area** — drag-and-drop / file-picker for one CSV. On success shows the profile card.
  Real: `POST /datasets`.
- **Dataset profile card** — column names, dtypes, row count, per-column ranges/stats, and
  missing-value counts (from `profile`). Real.
- **Ask box** — text input + send; submits the question for the active dataset. Real: `POST /ask`.
- **Answer panel** — the plain-English answer, with:
  - **Collapsible "Show plan"** — the agent's numbered plan. Real.
  - **Collapsible "Show code"** — the exact generated pandas (monospace, syntax-styled). Real.
  - **Collapsible "Show result preview"** — the head-truncated result table/scalar. Real.
  - **Suggested follow-ups** — 2-3 clickable chips that pre-fill the ask box. Real.
- **Conversation thread** — prior turns in this session shown above the ask box (conversation
  memory is a P1 capability). Real.
- **Loading state** — a spinner + "Working…" while the agent runs (the *live step trail +
  streaming + timer* is a STUB until P3; P1 shows a simple working indicator, clearly the
  non-streaming version).

**Key elements — labelled STUBS in Phase 1 (become real in the noted phase):**

- **Dataset Library** (sidebar list of datasets to switch between) — STUB → real in P2.
  Badge: "Coming soon — your uploaded datasets will live here."
- **Run History browser** (per-dataset past questions/code/results) — STUB → real in P2.
- **Cost tracker / daily total** (tokens + estimated $ per query, running daily total) —
  STUB → real in P2.
- **Interactive charts** (auto-selected bar/line/scatter/pie, zoom/hover/filter) — STUB → real
  in P3. Badge in the answer panel: "Chart coming soon."
- **Live step trail + streaming answer + elapsed timer** — STUB → real in P3.
- **Column notes / business rules editor** — STUB → real in P4.
- **Multi-file join / Excel multi-sheet picker** — STUB → real in P4.

**Actions available (P1):** upload a CSV; ask a question; expand/collapse plan/code/result;
click a suggested follow-up.

## Error States

- **Upload errors** (bad file, too large, parse failure) → inline red banner with the
  `error.message` from the envelope; the upload area stays usable.
- **Ask errors** (LLM unavailable, run failed) → red banner in the answer panel with the
  message; the question stays in the box so it can be retried.
- **Agent best-guess / uncertainty** (P4) → the answer panel renders an "uncertain — best
  guess" badge; clarify prompts (P4) render as a question the user answers as a new turn.
- **Loading** → working indicator on submit; inputs disabled during the run.
- **Empty states** → before any upload, the main column shows a friendly "Upload a CSV to begin"
  prompt; before any question, the answer panel shows "Ask a question about your data."

## Tech Stack

Next.js 15 + React 19 + Tailwind CSS, static export (`output: 'export'`, `basePath: '/app'`),
served single-origin by FastAPI. Charting library (Phase 3) chosen by the generator (e.g.
Recharts or Plotly) — interactive (zoom/hover/filter). See
[architecture.md → Stack](architecture.md).
