# UI

> The DataChat web chat interface. One screen: upload a file, chat about it, see charts inline. Phase 1 ships a polished, real chat for the core path plus clearly-labelled NON-FUNCTIONAL stubs for later features — styled as "Coming soon", never as broken.

---

## UI Type

Browser chat interface — a single-page Next.js static export served at `http://localhost:8001/app/`. Replaces the existing transform form in `frontend/src/app/page.tsx`.

## Views / Screens

### Screen: Chat Workspace (the only screen)

**Purpose:** Upload a dataset, ask questions about it in a chat, and see plain-language answers with inline charts.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  DataChat                          [Connect a live DB ▸] │  ← stub (badge: Coming soon)
├──────────────┬──────────────────────────────────────────┤
│  SIDEBAR     │   MESSAGE THREAD                          │
│              │                                           │
│  Upload area │   user: what were total sales by region? │
│  (dropzone)  │   assistant: Total sales were highest…    │
│              │     ┌───────────────────────────────┐    │
│  Detected    │     │  [ inline bar chart ]         │    │
│  schema:     │     └───────────────────────────────┘    │
│   region str │   user: break that down by month         │
│   sales  num │   assistant: …  [ inline line chart ]    │
│   date   date│                                           │
│  1,240 rows  │                                           │
│              │                                           │
│  ── Coming   ├──────────────────────────────────────────┤
│     soon ──  │  [ type a question…            ] [ Ask ]  │
│  • Deep mem  │                                           │
│  • Insights  │   [chart-type toggle: bar|line|pie] ◦disabled
│  • Chart ctl │                                           │
└──────────────┴──────────────────────────────────────────┘
```

**Key elements (REAL in Phase 1):**
- **Upload dropzone** — drag/drop or click to select a CSV/`.xlsx`. On success, shows the detected schema (column names + types) and row count. Calls `POST /datasets`.
- **Message thread** — alternating user/assistant bubbles, scrollable, newest at bottom.
- **Inline chart** — rendered with Recharts directly under the assistant message when the response includes a `chart` spec (bar/line/pie chosen by the agent).
- **Question input + Ask button** — sends `POST /chat` with `dataset_id`, `question`, and `conversation_id`. Disabled until a dataset is uploaded.

**Key elements (NON-FUNCTIONAL STUBS — labelled "Coming soon"):**
- **"Connect a live database ▸"** button (top-right) — disabled, badge "Coming soon" (Phase 4).
- **"Deep memory"** indicator in the sidebar — static "Coming soon" chip (Phase 2).
- **"Auto-insights"** panel placeholder in the sidebar — greyed card reading "Insights it finds on its own — coming soon" (Phase 3).
- **Chart-type toggle** (bar | line | pie) under the input — visibly disabled with a tooltip "The agent picks the best chart — manual control coming soon" (deferred chart controls).

**Actions available:**
- Upload a file → see schema.
- Type a question → receive an answer (+ optional chart).
- Scroll the thread.
- (Stubs are inert — clicking shows a "Coming soon" affordance, never an error.)

## Auto-Chart Behavior

The user never picks a chart type in Phase 1 — the agent decides (bar for comparison, line for trend, pie for distribution, none for single-value answers) and returns a `ChartSpec`. The UI renders whatever `chart.type` it receives. When `chart` is `null`, only the text answer shows. The disabled chart-type toggle communicates that manual override is a future feature, not a missing one.

## Error States

- **Upload error** (bad type / unreadable): inline red notice in the sidebar ("Couldn't read that file — please upload a CSV or .xlsx").
- **Chat error** (LLM/aggregation failure): an assistant-style error bubble in the thread ("I couldn't answer that — try rephrasing"), not a crash; input stays usable.
- **Loading:** an animated "Thinking…" assistant bubble while `POST /chat` is in flight; a spinner on the dropzone during upload.
- **Network error:** a toast/inline notice ("Network error — is the server running?").

## Tech Stack

Next.js 15 + React 19, Tailwind, **Recharts** for charts, static export built via `cd frontend && pnpm build` → `frontend/out/`, served by FastAPI at `/app`. Components live under `frontend/src/components/`.
