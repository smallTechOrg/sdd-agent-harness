# UI

---

## UI Type

Web app (single page) — Next.js 15 static export served by FastAPI at `http://localhost:8001/app/`. Single-user, browser-based. A three-region layout: left **Library sidebar** (stub in Phase 1), center **chat + answers**, top-right **cost meter**.

## Views / Screens

### Screen: Workspace (the one page)

**Purpose:** Upload a file, see its profile, ask questions, watch live reasoning, read answers, browse history.

**Key elements:**
- **Upload / dropzone** — drag a CSV/Excel in; shows progress, then swaps to the profile panel.
- **Profile panel** — columns + dtypes + ranges + data-quality flags from the auto-profile; collapsible.
- **Chat thread** — the session's Q&A turns; the input box accepts plain-language questions; follow-ups understand prior context.
- **Live step viewer** — while a question runs, streams each step (plan / write code / run / inspect / refine) with status (tried / failed / worked) and a **`Step N of M` counter**. Plan is shown before code executes.
- **Answer card** (per answer) — prose with key numbers; an **interactive chart** (Recharts: zoom/hover/tooltip; agent-picked type); a **results table** beside the prose; a collapsible **"Show code"** revealing the exact pandas; an uncertainty note when the agent flagged unsureness or hit the step limit.
- **Suggested follow-ups** — 2–3 clickable follow-up questions under each answer.
- **Cost meter** (top-right) — estimated cost + tokens for the last question, and the **running daily total**.
- **History drawer** — per-dataset list of past runs; clicking one reopens its full detail (plan, steps, code, chart, table).
- **Labelled stubs (Phase 1, NON-FUNCTIONAL, visibly tagged):**
  - **Library sidebar** — greyed list with a "Dataset Library — coming in Phase 2" badge.
  - **"Add file / Join files"** button — disabled with a "Multi-file joins — coming in Phase 3" tooltip.

**Actions available:**
- Upload a file; ask a question; click a suggested follow-up; expand/collapse code and profile; open the history drawer; hover/zoom the chart.

## Error States

- **Upload error** (bad type/too big): inline red banner on the dropzone with the reason.
- **Run error** (LLM/exec fatal): the live step viewer shows the failed step in red and the answer card shows a surfaced error message; the partial run is still saved to history.
- **Clarification:** instead of an answer, the card shows the agent's clarifying question and invites the user to reply as a new turn.
- **Loading/streaming:** the step viewer is the loading state (live steps), never a blank spinner; the input is disabled while a run streams.
- **Network error:** "Network error — is the server running?" banner.

## Tech Stack

Next.js 15 + React 19 + Tailwind v4 + Recharts (interactive charts). SSE consumed via `EventSource`/fetch-stream for the live step viewer. Playwright E2E in `frontend/tests/e2e/`. Follows the static-export rules in `harness/patterns/tech-stack.md` (keep `postcss.config.mjs` + `@source` in globals.css; `basePath:'/app'`).
