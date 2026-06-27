# UI

---

## UI Type

Web app — a single-page Next.js 15 / React 19 / Tailwind interface, static-exported and served at `http://localhost:8001/app/`. Single user, no login.

## Views / Screens

### Screen: Analyze (single page)

**Purpose:** Upload a CSV, see its schema, ask a plain-English question, read the answer.

**Key elements (REAL in Phase 1):**
- **Upload panel** — file picker (restricted to `.csv`) + "Upload" action. After upload: shows filename, row count, and the detected column list (name + friendly dtype).
- **Ask panel** — a text input ("Ask a question about your data…") + "Ask" button. Enabled only once a dataset is uploaded.
- **Answer panel** — renders the plain-English answer; shows a loading state while Gemini responds; shows human-readable error copy on failure.
- **Privacy note** — a short, visible line: "Your data stays on your machine — only a summary and your question are sent to the AI." This makes the dealbreaker guarantee visible to the user.

**Key elements (LABELLED NON-FUNCTIONAL STUBS in Phase 1 — must look intentional, never like a bug):**
- **Charts** — a card titled "Charts & visual summaries" with a greyed-out illustrative placeholder and a `Coming in Phase 2` badge; clicking is disabled or shows a "coming soon" tooltip. Wired up in Phase 2.
- **Insights / Anomalies** — a card titled "Automatic patterns & anomalies" with a `Coming in Phase 3` badge, similarly disabled.
- **Connect a database** — a card marked `Not planned — CSV only` (out of scope/deferred per intake), visibly distinct from the "coming soon" cards so the user understands it is intentionally excluded.

**Actions available:**
- Upload a CSV.
- Ask a question (after upload).
- (Stubs are non-interactive / disabled.)

## Error States

- **Upload failure** (bad CSV / too large): inline red banner with human copy from the API ("Could not read this file as CSV").
- **Ask failure** (unknown dataset / Gemini down): the answer panel shows human-readable error copy, never a stack trace.
- **Loading:** upload and ask each show a spinner/disabled state while in flight.
- **Network error:** "Network error — is the server running?" (skeleton pattern).

## Tech Stack

Next.js 15 + React 19 + Tailwind, static export to `frontend/out`, mounted at `/app` by FastAPI (single origin — no CORS, relative `fetch` paths). Replaces the skeleton's transform form in `frontend/src/app/page.tsx`.
