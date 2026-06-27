# UI

## UI Type

Web dashboard — single-page application (Next.js 15 static export). Single view with a persistent sidebar and a main panel that switches between upload mode and analysis mode.

---

## Layout

```
┌──────────────────────────────────────────────────────┐
│  [Sidebar — 280px]  │  [Main Panel — remaining width] │
│                     │                                  │
│  Upload History     │  Upload Panel  OR                │
│  ─────────────      │  Analysis Panel + Results Panel  │
│  file1.csv          │                                  │
│  1500 rows · 8 cols │                                  │
│  Jun 28 10:30       │                                  │
│  ─────────────      │                                  │
│  file2.xlsx         │                                  │
│  …                  │                                  │
│                     │                                  │
│  [+ Upload New]     │                                  │
└──────────────────────────────────────────────────────┘
```

The sidebar is always visible. The main panel shows the Upload Panel when no file is selected, and the Analysis Panel + Results Panel once a file is active.

---

## Views / Screens

### Screen: Upload Panel

**Purpose:** The user selects or drops a file to upload. This is the initial state when the app loads or when the user clicks "+ Upload New" in the sidebar.

**Key elements:**
- Drag-and-drop zone: a dashed-border rectangle labelled "Drop a CSV or Excel file here, or click to browse". Accepts `.csv`, `.xlsx`, `.xls`.
- File picker button inside the drop zone (triggers native file picker).
- Size limit note: "Max 50 MB" displayed beneath the drop zone.
- Loading state: once a file is chosen, the drop zone shows a spinner and "Uploading…" text. The file picker is disabled during upload.
- On success: the drop zone is replaced by a confirmation card showing filename, row count, column count, and a brief column list. The analysis panel becomes visible below.
- On error: an inline error card replaces the drop zone showing the error message and a "Try Again" button.

**Actions available:**
- Drop a file onto the drop zone
- Click to open the native file picker
- Select a file (triggers immediate upload; no separate "confirm" step)

---

### Screen: Analysis Panel

**Purpose:** After a file is uploaded (or selected from history), the user configures and runs an analysis.

**Key elements:**

- File header: filename, row count, col count displayed at the top of the main panel.
- Analysis type dropdown. Options in Phase 1:
  - "Summary Statistics" (active — real in Phase 1)
  - "Trend Over Time — Coming in Phase 2" (disabled; greyed out with badge)
  - "Top / Bottom N — Coming in Phase 2" (disabled; greyed out with badge)
  - "Correlation — Coming in Phase 2" (disabled; greyed out with badge)
  - "Ask a Question — Coming in Phase 3" (disabled; greyed out with badge)
- Dynamic parameter form (shown below the dropdown, changes based on selected type):
  - `summary_stats`: no params — form area shows "No parameters needed."
  - `trend_over_time` (Phase 2): date column selector (dropdown of column names), value column selector (dropdown of numeric columns only).
  - `top_bottom_n` (Phase 2): column selector (any column), N input (number, 1–100), direction toggle ("Top" / "Bottom").
  - `correlation` (Phase 2): column A selector (numeric columns only), column B selector (numeric columns only).
  - `nl_query` (Phase 3): a multi-line text input labelled "Ask a question about this data…", placeholder "e.g. What is the average sales by region?"
- "Run Analysis" button: enabled only when required params are filled.
- Loading state: button becomes "Running…" and is disabled while the analysis is in progress.

**Actions available:**
- Select analysis type from dropdown
- Fill in parameters (column selectors, N input, question box)
- Click "Run Analysis"

---

### Screen: Results Panel

**Purpose:** Displays the output of a completed analysis. Appears below the Analysis Panel after Run is clicked.

**Key elements:**

- Summary card: a bordered card with a heading "Summary" and a paragraph of plain-English text from `data.summary`.
- Chart area: if `data.chart_json` is non-null, a Plotly chart is rendered client-side using `plotly.js`. The chart is interactive (zoom, pan, hover tooltips). Chart area height is fixed at 400px.
- Table area: if `data.table` is non-null, a paginated table (20 rows per page) with column headers and row data. Columns are auto-sized. Page controls appear below the table when there are more than 20 rows.
- Error card: if `data.status == "failed"`, the summary card is replaced by a red-bordered error card showing `data.error_message` and a "Try Again" button that resets the Analysis Panel.
- Loading skeleton: while the analysis is running, the Results Panel shows a placeholder skeleton (grey animated bars where the summary card, chart, and table will appear).

**Actions available:**
- Interact with the Plotly chart (zoom, pan, hover)
- Page through the table (next/previous page buttons)
- Click "Try Again" on error to re-run with the same or different params

---

### Screen: Sidebar — Upload History

**Purpose:** Shows all previously uploaded files. Lets the user switch between uploads without re-uploading.

**Key elements:**
- List of upload cards (one per upload), ordered newest first. Each card shows:
  - Filename (truncated at 32 chars with ellipsis if longer)
  - Row count and column count ("1500 rows · 8 cols")
  - Upload timestamp (relative: "2 hours ago"; absolute on hover)
- Active upload highlighted with a blue left border.
- "+ Upload New" button at the bottom (or top) of the sidebar. Clicking resets the main panel to the Upload Panel.
- Empty state: "No uploads yet. Upload a file to get started."

**Actions available:**
- Click an upload card to make it the active file (the Analysis Panel appears in the main panel with that file's columns)
- Click "+ Upload New" to start a fresh upload

---

## Stub Labels (Phase 1)

Disabled analysis type options in the dropdown carry a visual badge to distinguish them from bugs:

- Badge text: "Phase 2" for trend/top-bottom/correlation; "Phase 3" for NL query.
- The dropdown option is grey and non-clickable (disabled attribute).
- No tooltip or explanation is required — the badge text is self-explanatory.

---

## Error States

| Error situation | UI response |
|-----------------|-------------|
| Upload fails (file too large) | Inline error card in Upload Panel with the error message and "Try Again" button |
| Upload fails (unsupported format) | Same inline error card |
| Upload fails (server error) | Same inline error card with "Server error — check the console" |
| Analysis returns status=failed | Red error card in Results Panel with error_message and "Try Again" button |
| Network error (server not running) | Toast notification or inline banner: "Cannot reach the server. Is it running on port 8001?" |
| File picker cancelled | No state change — drop zone remains in its prior state |

All error states include a clear path back to the prior state (Try Again button, or clicking a sidebar entry).

---

## Responsive Behaviour

- Desktop (≥1024px): sidebar 280px fixed, main panel fills remaining width.
- Tablet (768px–1023px): sidebar collapses to a 48px icon rail; main panel full width. Tapping the rail icon expands the sidebar as an overlay.
- Mobile (<768px): sidebar hidden by default, accessible via a hamburger menu button in the top navigation bar.

---

## Technology

Next.js 15 + React 19 + Tailwind v4 (existing skeleton). The static export is built with `pnpm build` and served by FastAPI at `/app`. Chart rendering uses `plotly.js-dist-min` (client-side only, imported dynamically to avoid SSR issues). All data fetching is via `fetch` against the FastAPI backend at the same origin (no CORS issues in single-origin mode).

> All fetch calls use relative URLs (e.g. `/uploads`, `/analyses`) — not `http://localhost:8001/...` — so the frontend works correctly when served by FastAPI at `/app`.
