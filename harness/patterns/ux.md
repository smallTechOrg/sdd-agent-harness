# UX Patterns — building interfaces that delight

A UI that passes tests but doesn't delight is a failed delivery. The harness builds products,
not proofs-of-concept. This file is the UX floor — every interface must clear it before the
iteration gate, and the FR must specify the experience at this level of detail.

The test: **could you demo this to a user who has never seen it and have them say "wow" in
2 minutes?** If not, the quality bar is not met.

---

## The four states every interactive element must handle

Every data-bearing component — a query result, a dataset list, a chart — must be designed for
four states, not one. A component that only handles the happy path ships half a product.

| State | What the user sees | Implementation note |
|-------|--------------------|---------------------|
| **Loading** | A skeleton or spinner — never a blank area or layout shift | `animate-pulse` skeleton divs that match the expected content shape |
| **Empty** | An instructive empty state — what to do next, not just "no results" | A call-to-action or example, never a blank table or silent `[]` |
| **Populated** | The actual content, styled to scan at a glance | See component standards below |
| **Error** | A plain-English error with a recovery action | Never expose a stack trace or raw error string to the user |

---

## Data tables

A raw HTML `<table>` is not acceptable as a final deliverable. Every data table must:

- Be **sortable** — clicking a column header toggles asc/desc sort
- Show **row count** in the header (`42 rows`)
- **Paginate or virtualise** for > 50 rows — never dump 10,000 rows into the DOM
- Have **column type indicators** — a number column right-aligns; a date column formats `YYYY-MM-DD`
- Highlight **null / empty cells** visually (light grey background or `—` placeholder)
- Support **copy-to-clipboard** on a cell value (click to copy)

Use Tailwind utility classes. A table built with bare `<table><tr><td>` with no classes is not done.

---

## Charts and data visualisation

Charts must be **interactive**, not static images.

- Use Plotly via `react-plotly.js` with `dynamic(() => import(...), { ssr: false })`
- Default chart type by data shape: line for time-series, bar for categorical, scatter for two
  numeric columns — do not default everything to a bar chart
- Every chart must have: a **title** (derived from the query), **axis labels**, **hover tooltips**
  with the exact value, and a **download as PNG** button (Plotly provides this in the modebar)
- For dashboards with multiple charts: use a **responsive CSS grid** (`grid-cols-1 md:grid-cols-2`)
  with consistent card sizing; charts must not overflow their containers
- Show a "No data to chart" empty state rather than an empty Plotly canvas

---

## Query / response flow

The moment a user submits a query, the interface must show progress — never a silent wait.

1. **Submit** → button becomes disabled + spinner; input remains readable (don't clear it)
2. **Streaming / polling** → if the backend streams, render tokens as they arrive; if it
   polls, show an animated "thinking…" indicator with elapsed seconds
3. **Response rendered** → Markdown table via `react-markdown` + `remark-gfm` (not `<pre>`),
   chart below it, follow-up suggestions as clickable chips underneath the chart
4. **Error** → inline below the input in red, with a "Try again" button; never replace the
   previous result with the error

Follow-up suggestion chips must be **clickable** — clicking one fills the input and submits.
They are not decorative labels.

---

## Session and history

- Every session has a **visible session ID or name** in the sidebar — even if it's just
  `Session 3` or a UUID truncated to 8 chars
- Switching sessions loads that session's history — the query input does not clear
- The active session is **highlighted** in the sidebar (not just listed)
- A new session starts automatically when the user opens a new tab (per-tab isolation)
- Session history shows each query + response collapsed to one line; expanding shows the full
  response without a page reload

---

## Stub mode

The stub-mode banner is a **product requirement**, not a technical detail.

- Yellow background, full-width, top of page — not a small badge
- Text: **"STUB MODE — responses are canned, not real AI output"** (or equivalent)
- Must be **immediately visible** without scrolling on any viewport
- Disappears automatically when a real LLM key is configured — do not require a manual dismiss

---

## Typography and spacing

- Use a **sans-serif body font** at 14–16px for data; do not use the browser default unstyled
- Code, SQL, and model names use a **monospace font** (`font-mono` in Tailwind)
- Section headings are **bold** and visually separated from content — not the same weight as body
- Minimum **8px padding** inside all interactive elements (buttons, inputs, cards)
- Interactive elements have a **hover state** — a button with no hover feedback feels broken

---

## Accessibility floor

Not an exhaustive a11y audit — the minimum that prevents obvious failures:

- Every `<input>` has an associated `<label>` (not just placeholder text)
- Buttons have descriptive text or an `aria-label` — not just an icon with no label
- Color is **never the only indicator** of state (error state has both red colour and an icon/text)
- Tab order follows the visual reading order

---

## What "done" looks like for a UI step

A UI step is not done when the component renders without crashing. It is done when:

1. All four states (loading, empty, populated, error) are implemented and tested
2. The component can be demoed in 2 minutes and produces a genuine reaction from a new viewer
3. The golden-path demo script in the FR (see researcher.md) runs without the demonstrator
   having to explain why something looks unfinished
4. The reviewer has loaded the actual page in a browser (not just confirmed `curl :3000/` → 200)
