# UI

## UI Type

Single-page chat interface. Web dashboard with a two-panel layout: a left sidebar for file management and a main chat panel for question-answer history with inline charts. Served as a Next.js 15 static export at `http://localhost:8001/app/`.

---

## Views / Screens

### Screen: Main Layout (single page)

**Purpose:** The only screen. Contains all functionality in a two-panel layout. The user never navigates away from this page.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [App Title: "Data Analysis Agent"]                         │
├──────────────────────┬──────────────────────────────────────┤
│  LEFT SIDEBAR        │  CHAT PANEL                          │
│  (fixed width ~280px)│  (flexible width, fills remaining)   │
│                      │                                      │
│  [Upload Zone]       │  [Answer History]                    │
│  [File List]         │  ...scrollable...                    │
│  ─────────────────   │                                      │
│  [PG Connect stub]   │  [Question Input Bar]                │
└──────────────────────┴──────────────────────────────────────┘
```

---

### Component: Left Sidebar

**Purpose:** File management. Upload files, view uploaded files, and see the PostgreSQL stub.

**Key elements:**

1. **Upload Zone** (Phase 1 — real)
   - Drag-and-drop target with a dashed border and icon
   - Text: "Drop a CSV here or click to browse"
   - Also accepts click-to-browse (file input `accept=".csv,.xlsx,.xls"`)
   - On drag-over: border color changes to blue, background becomes light blue
   - On file drop/select: immediately calls `POST /api/files/upload` with a loading spinner overlay on the zone
   - On success: Schema Preview Modal appears (see below); file appears in the file list
   - On error: red error message below the upload zone ("Upload failed: [error message]")

2. **File List** (Phase 1 — real)
   - Scrollable list of uploaded files, newest first
   - Each item shows: filename, source type badge (`CSV` in green), row count, upload date
   - Clicking a file item makes it the "active file" for subsequent questions (highlighted with a blue left border)
   - Active file name shown in the question input area as context ("Asking about: sales_data.csv")
   - Empty state: "No files uploaded yet. Drop a CSV above to get started."

3. **PostgreSQL Connect Section** (Phase 1 — stub; Phase 2 — real)
   - Section header: "Data Sources"
   - Button: "Connect PostgreSQL" with a database icon
   - Phase 1 stub appearance: button is disabled (grayed out), badge next to it reads "Coming in Phase 2" in an amber color
   - Phase 1 stub behavior: clicking it shows a tooltip "PostgreSQL connection coming in Phase 2"
   - The stub is visually distinct from the file list so users immediately understand it's a labeled placeholder, not a broken feature

---

### Component: Schema Preview Modal

**Purpose:** Shown immediately after a file is successfully uploaded, before the user asks a question. Confirms the file was read correctly.

**Trigger:** Automatically shown on successful `POST /api/files/upload` response.

**Key elements:**
- Modal overlay (centered, dismissible by clicking outside or pressing Escape)
- Title: "Schema Preview — [filename]"
- Column table: column name, detected data type (e.g. `float64`, `object`, `int64`)
- Sample rows: first 3 data rows in a table grid
- Row count and file size shown below the table
- "Start Analyzing" button — dismisses modal and focuses the question input
- "Close" (X) button — dismisses modal; user can ask questions later

---

### Component: Chat Panel — Question Input Bar

**Purpose:** The user types a plain-English question here.

**Key elements:**
- Fixed to the bottom of the chat panel
- Text input (single line; expands to multi-line on Shift+Enter)
- Placeholder text: "Ask a question about [active filename]..." (or "Upload a file to get started" when no file is active)
- **Send button** — disabled when: (a) no file is active or (b) input is empty or (c) a run is in progress
- Keyboard shortcut: Enter submits (Shift+Enter adds newline)
- On submit: input is cleared, a loading AnswerCard appears in the history above

---

### Component: Chat Panel — Answer History

**Purpose:** Scrollable list of all question/answer pairs for the current session.

**Key elements:**
- Newest answers appear at the bottom (chat-style, scrolls down automatically)
- Empty state: "Upload a CSV and ask your first question." (shown when no history)
- Each entry is an AnswerCard (see below)

---

### Component: AnswerCard

**Purpose:** Displays one question + answer pair.

**Key elements:**

1. **Question bubble** — right-aligned, user's question text, timestamp
2. **Answer section** — left-aligned card containing:
   - Text answer (rendered as plain text; no markdown parsing required in Phase 1)
   - Inline Plotly.js chart (see ChartPanel below)
   - Metadata footer: run duration (e.g. "Answered in 14.2s"), file name used
3. **Loading state** — while the run is in progress:
   - Question bubble appears immediately
   - Answer section shows a pulsing skeleton / spinner with text "Analyzing..."
4. **Error state** — if the run returns `status: "failed"`:
   - Red error card with icon and message: "Analysis failed: [error message]"
   - No chart is shown

---

### Component: ChartPanel

**Purpose:** Renders one Plotly.js chart inline inside an AnswerCard.

**Key elements:**
- Container `<div>` with a fixed height of 350px and `width: 100%`
- On mount: calls `Plotly.newPlot(divId, chart_spec.data, chart_spec.layout, {responsive: true, displayModeBar: true})`
- Chart is fully interactive: zoom (scroll wheel), pan (click-drag), hover tooltips, download PNG (Plotly's built-in toolbar)
- If `chart_spec` is null: ChartPanel is not rendered (text-only answer card)
- On Plotly.js load error (rare): shows "Chart unavailable" text with the raw data as a simple table

---

## Loading States

| Action | Loading Indicator |
|--------|------------------|
| File upload | Spinner overlay on the UploadZone; "Uploading..." text |
| Analysis run in progress | Pulsing skeleton card in the answer history with "Analyzing..." text; Send button disabled |
| App initial load (file list) | Skeleton list items in the sidebar while `GET /api/files` loads |

---

## Error States

| Error | Display Location | Appearance |
|-------|-----------------|------------|
| Upload failed (bad format) | Below UploadZone | Red inline message: "Upload failed: [message]" |
| Upload failed (server error) | Below UploadZone | Red inline message with retry suggestion |
| Analysis run failed (LLM error) | AnswerCard | Red card with: "Analysis failed: [error_message]" |
| Analysis run failed (code error) | AnswerCard | Red card with: "Code execution failed: [error_message]" |
| Network error (fetch failed) | Below question input | Red banner: "Network error — is the server running?" |
| No file selected when submitting | Question input | Input border turns red; tooltip: "Please upload and select a file first" |

Error states are always explicit and descriptive — no silent failures, no generic "Something went wrong."

---

## Labelled Stubs (Phase 1 — Not Bugs)

The following UI surfaces are **deliberately non-functional** in Phase 1 and must be **visually labelled** so users immediately understand they are planned features, not broken functionality:

| Surface | Label | Appearance |
|---------|-------|------------|
| "Connect PostgreSQL" button | "Coming in Phase 2" badge in amber | Grayed-out button + amber badge |
| Session history persistence | Not labelled separately — the sidebar note reads: "Files reset on server restart (Phase 2)" | Subtle italic text below the file list |

These stubs are wired as Phase 2 deliverables per `spec/roadmap.md`.

---

## Routing

Single page — no client-side routing needed. The entire app lives at `/app/` (with trailing slash, due to `trailingSlash: true` in `next.config.ts`).

## Responsive Behavior

- Desktop-first design (personal tool, typically used on a laptop/desktop)
- Minimum supported width: 1024px
- Sidebar collapses to an icon drawer on screens < 768px (nice-to-have; not a Phase 1 requirement)
