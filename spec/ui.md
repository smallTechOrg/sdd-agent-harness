# UI

> Single-screen web app served at `http://localhost:8001/app/`. Next.js 15 static export. The Phase-1 screen delivers the full primary journey (upload → profile → ask → answer + chart + table + show-its-work) and shows ALL later features as clearly-labelled non-functional stubs.

---

## UI Type

Web app (single page, local). Built from the skeleton's `frontend/`, replacing the transform form in `frontend/src/app/page.tsx`.

## Views / Screens

### Screen: Analyst (the single Phase-1 screen)

**Purpose:** Upload a dataset, see its profile, ask a question, and read the answer with its chart, table, and reasoning.

**Layout:**
- **Left sidebar — Datasets (STUB in Phase 1 → REAL in Phase 2):** in Phase 1, shows the current dataset only, with a greyed "Past datasets — coming soon" stub list. **Phase 2 makes this a real switchable list** (see the Phase-2 sidebar section below).
- **Main column:**
  - **Uploader (REAL):** drag/drop or pick a `.csv`. Beside it: a greyed "Excel (.xlsx) — coming soon" note (STUB, Phase 5).
  - **Profile card (REAL):** appears after upload — row count, a table of columns (name + inferred type), and a health summary (nulls / distincts / numeric ranges).
  - **Ask box (REAL):** a text input + "Ask" button for ONE question. Below it: a greyed "Suggested questions" chip row (STUB, Phase 6) and a disabled "Ask a follow-up" affordance labelled "coming soon" (STUB, Phase 3).
  - **Answer panel (REAL):** plain-English answer with key numbers emphasized; ONE auto-picked chart (bar/line/pie via Recharts, or table-only); a compact summary table.
  - **Show its work (REAL, collapsible):** the plan, the step trace (each step ok/failed with any recovered SQL error shown), and the exact DuckDB SQL that ran. Per-question cost shown here (REAL).
  - **Compare another file (STUB, Phase 4):** a greyed button labelled "coming soon".
  - **Column notes (STUB, Phase 5):** a greyed panel labelled "coming soon".
  - **Daily cost (STUB, Phase 6):** a small figure showing "—" with a "coming soon" tooltip. (Per-question cost is real; the daily roll-up is the stub.)

**Actions available:**
- Upload a CSV → see the profile.
- Type a question → Ask → see the answer + chart + table + trace.
- Expand/collapse "Show its work".

### Phase 2 additions: Dataset browser + run history (REAL)

> Phase 2 turns the greyed "Past datasets" sidebar stub into a real, switchable list and adds a run-history affordance. Everything else stays a clearly-labelled "coming soon · Phase N" stub — a stub must never read as a bug.

**Sidebar — Past datasets (REAL in Phase 2):**
- A real list of every uploaded dataset, **newest first**, populated from `GET /datasets`. Each item shows: **name**, **row count**, and **question count** (e.g. "sales.csv · 124,000 rows · 5 questions"). A `failed`-ingest dataset is shown distinctly (the `status` field), not hidden.
- **Clicking a dataset selects it** → the UI calls the existing `GET /datasets/{id}` to re-load that dataset's full **profile card** (re-rendering the Phase-1 profile view) and `GET /datasets/{id}/runs` to populate its run history. The selected dataset becomes the **active dataset for new questions** (the Ask box now targets it).
- **Active-dataset indicator:** the selected item is visually highlighted (e.g. the existing current-dataset blue treatment) so it's always clear which dataset new questions will run against.

**Run history (REAL in Phase 2):**
- For the selected dataset, a **list of prior questions** (from `GET /datasets/{id}/runs`, newest first). Each item shows the question text and a timestamp; failed runs are marked distinctly.
- **Clicking a past question re-opens that run** — its full persisted answer (answer + key numbers + chart + summary table + collapsible "show its work" with plan/trace/SQL/per-question cost) renders in the existing **answer panel**, reconstructed from the persisted record. **No new question is asked and no LLM call is made** — re-opening history is instant and free. The re-opened run renders identically to when it was first answered (same `AnswerPanel`/`Chart`/`SummaryTable`/`ShowItsWork`).
- Asking a NEW question on the active dataset works exactly as in Phase 1 and appends to the top of the history list.

**Phase 2 list/history states:**
- **Loading:** a lightweight skeleton/spinner while `GET /datasets` (sidebar) or `GET /datasets/{id}/runs` (history) is in flight.
- **Empty:** "No past datasets yet" in the sidebar when the list is `[]`; "No questions yet for this dataset" in the history panel when runs is `[]`. Empty is a normal state, styled distinctly from an error (not red).
- **Error:** if a list/history fetch fails, a clear inline message (e.g. "Couldn't load your datasets — is the server running?"), red and distinct from the greyed stubs and from the empty state.

**Still STUBS after Phase 2 (clearly labelled "coming soon · Phase N", never look broken):**
- "Ask a follow-up" affordance — **Phase 3** (conversation memory).
- "Compare another file" button — **Phase 4** (multi-file JOIN).
- Excel (`.xlsx`) upload note + "Column notes" panel — **Phase 5**.
- "Suggested questions" chip row + daily-cost figure (shows "—") — **Phase 6**. (Per-question cost stays REAL in show-its-work.)

## Error States

- **Upload loading:** spinner + "Profiling your data…"; on failure a clear inline message (e.g. "Couldn't read that CSV — check it's a valid file"). A stub must never look like this error — stubs are visibly greyed/labelled, errors are red.
- **Ask loading:** live "working" indicator that updates as the agent progresses (planning → running SQL → writing answer), so the ~30s feels responsive.
- **Ask failure:** the answer panel shows the failure message AND the "show its work" trace stays available (so the user sees what was tried, incl. a SQL error that couldn't be corrected after retries).
- **Network error:** "Network error — is the server running?" (matches the skeleton's pattern).

## Tech Stack

Next.js 15 + React 19 + Tailwind v4 (skeleton), static export served by FastAPI at `/app/`. Charts via **Recharts** (added to `frontend/package.json`). E2E via **Playwright** (`frontend/tests/e2e/`).
