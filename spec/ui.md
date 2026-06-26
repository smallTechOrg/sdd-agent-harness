# UI

---

## UI Type

Single-screen web app — a Next.js 15 static export (React 19, Tailwind v4) served by FastAPI at `/app`. The canonical URL is **http://localhost:8001/app/**. It is `frontend/src/app/page.tsx` (replacing the skeleton transform form).

## Views / Screens

### Screen: Analyst (single page)

**Purpose:** Upload a CSV, ask a question, read the auditable answer.

**Key elements (top to bottom):**
- **Title + one-line intro** — "Local Data Analyst — your data stays on this machine."
- **CSV upload** — a file input that reads the chosen file with `FileReader.readAsText` into `csv_text`. Shows the file name and row/column hint once loaded. Rejects obviously non-CSV files with a friendly message before submit.
- **Mode toggle** (Phase 2+) — a toggle/selector control above the question input: "Analyze with: [Pandas (default)] [SQL]". User chooses one before asking a question. Defaults to Pandas. (Phase 1: omitted; all runs assume pandas.)
- **Question input** — a text box for the natural-language question.
- **Run button** — disabled until both a CSV and a question are present; shows a loading state while the request is in flight.
- **Answer card** (REAL) — the `answer` line plus the `explanation` paragraph.
- **"Show its work" panel** (REAL) — the `generated_code` rendered as a monospaced code block, and the `result_table` rendered as an HTML table (`columns` as headers, `rows` as cells). This satisfies constraint 2 (show its work) and is always visible alongside the answer.
- **Labelled NON-FUNCTIONAL stubs** (clearly marked "coming soon", visibly disabled/greyed — never look like bugs):
  - "Charts (coming soon)" — a greyed placeholder where a chart will render (wired in Phase 4).
  - "Connect a database (coming soon)" — a disabled control.
  - "Export results (coming soon)" — a disabled button.

**Actions available:**
- Choose a CSV file.
- Select a mode (Phase 2+): Pandas or SQL (Phase 1: pandas only, no visible toggle).
- Type a question.
- Submit (Run) → `POST /runs` with `{ csv_text, question, mode }` (mode defaults to `"pandas"` if not sent), read `data.data`.
- Read the answer, explanation, generated code (pandas snippet or SQL query), and result table.

## Error States

- **Loading:** Run button shows a spinner/"Analyzing…"; inputs disabled.
- **Validation (client):** if no file or no question, the button stays disabled; a non-CSV file shows "Please choose a .csv file."
- **Backend handled failure:** `data.status = "failed"` → show `data.error` in a red error card (e.g. "Couldn't read that as a CSV", "I don't see a column for that"), and still show `generated_code` if present so the attempt is visible.
- **Network/HTTP error:** show "Network error — is the server running?" (mirrors the skeleton pattern; reads `detail.message` on non-200).
- **Empty state:** before the first run, a muted "Upload a CSV and ask a question to get started."

## Tech Stack

Next.js 15 (static export, `output: 'export'`, `basePath: '/app'`) + React 19 + Tailwind v4 (requires `frontend/postcss.config.mjs`). Single-origin: the page fetches `/runs` on the same origin. Build with `cd frontend && pnpm build`; served by FastAPI. (See `harness/patterns/tech-stack.md` for the static-export/Tailwind/Node-version rules.)
