# UI

## UI Type

Single-page web chat interface. One URL: `http://localhost:8001/app/`. No routing. The layout is a three-column shell with a fixed sidebar, a scrollable main chat panel, and a fixed footer. Built as a Next.js 15 static export served by FastAPI.

---

## Views / Screens

### Screen: Main Application Shell

**Purpose:** The single screen the user sees for the entire application lifecycle. Contains all real and stubbed surfaces.

**Layout (three columns):**

```
┌──────────────────────────────────────────────────────────────────┐
│  SIDEBAR (240px fixed)    │  CHAT PANEL (flex-1)    │  (no 3rd)  │
│                           │                          │            │
│  [Upload CSV] button      │  Message bubbles         │            │
│  ─────────────────        │  (streaming text,        │            │
│  File list:               │   Plotly chart,          │            │
│  • sales_2025.csv ✓       │   code accordion)        │            │
│  • data.csv               │                          │            │
│                           │  [question input + Send] │            │
│  ─────────────────        │                          │            │
│  ┌─ STUB ──────────────┐  │                          │            │
│  │ Multi-file join      │  │                          │            │
│  │ [Coming in Phase 2]  │  │                          │            │
│  └──────────────────────┘  │                          │            │
│                           │                          │            │
│  ┌─ STUB ──────────────┐  │                          │            │
│  │ Session history      │  │                          │            │
│  │ [Coming in Phase 2]  │  │                          │            │
│  └──────────────────────┘  │                          │            │
│                           │                          │            │
└──────────────────────────────────────────────────────────────────┘
│  FOOTER: "Query: 1,240 in / 380 out tokens  |  $0.000298  "      │
└──────────────────────────────────────────────────────────────────┘
```

---

### Screen: File Sidebar (real in Phase 1)

**Purpose:** Let the user upload a CSV file and see all previously uploaded files.

**Key elements:**
- "Upload CSV" button — opens the OS file picker, accepts `.csv` only in Phase 1, `.csv,.xlsx` in Phase 3.
- Upload progress indicator (spinner) while `POST /api/files/upload` is in flight.
- File list: one row per file showing `original_filename`, `row_count` rows, and `created_at` date. Clicking a file row selects it (highlights it and pre-fills `file_ids` for the next query).
- Active file indicator: a checkmark or highlight on the currently selected file.

**Actions:**
- Click "Upload CSV" → opens file picker → file uploads → profile panel flashes in the chat area with the profile result.
- Click a file in the list → selects it for the next query.

---

### Screen: Profile Display (real in Phase 1)

**Purpose:** Show the auto-profile immediately after a file is uploaded.

**Key elements:** Displayed as an agent message bubble in the chat panel immediately after upload completes.
- File name and size.
- Table: column name | dtype | null count | 3 sample values.
- Row count and column count summary line.

---

### Screen: Chat Panel — Message Thread (real in Phase 1)

**Purpose:** Show the conversation history for the current browser session: user messages, agent streaming answers, charts, and code steps.

**Key elements:**
- **User message bubble:** Right-aligned, shows the question text.
- **Agent streaming message:** Left-aligned. Contains:
  - Streaming plain-text narrative (tokens appear in real time as the SSE `token` events arrive).
  - **Plotly chart:** Rendered inline after the text when the `chart` SSE event arrives. Interactive (zoom, hover tooltips, legend toggle). Chart type is auto-selected by the agent (bar, line, scatter, histogram, heatmap, or pie).
  - **Code accordion:** A collapsible "Show code steps (N steps)" disclosure element below each answer. Expanding it shows each `ExecutionStep` with iteration number, the Python code block (syntax-highlighted), stdout, and any stderr.
- **Thinking indicator:** A pulsing "Analysing…" indicator shown during the streaming phase before the first token arrives.
- **Error bubble:** If the SSE stream emits a `type:"error"` event, display it as a red agent bubble with the error message.
- **Clarification bubble:** If the SSE stream emits `type:"clarification"`, display it as an agent bubble with the question; the user's next typed message is treated as the reply.

---

### Screen: Question Input (real in Phase 1)

**Purpose:** Let the user type and submit a natural-language question.

**Key elements:**
- Single-line text input with placeholder "Ask a question about your data…"
- "Ask" button (disabled while a stream is in flight or no file is selected).
- Pressing Enter also submits.
- The input is cleared after submission.
- If no file is selected, shows an inline validation message "Please select a file first."

---

### Screen: Cost Footer (real in Phase 1)

**Purpose:** Display per-query token count and estimated cost.

**Key elements:**
- Updates after each completed query (on the `cost` SSE event).
- Format: `"Tokens: 1,240 in / 380 out  |  Cost: $0.000298"`
- In Phase 3, adds: `"Daily total: $0.00412"`

---

### Screen: Multi-File Panel (LABELLED STUB in Phase 1)

**Purpose:** Placeholder for Phase 2 multi-file join/compare/stack UI.

**Phase 1 appearance:**
- Visible in the sidebar below the file list.
- Grey, slightly desaturated style.
- Label: "Multi-file join — coming in Phase 2".
- No interactive elements respond to clicks.
- Not mistakable for a broken feature — the label makes it explicit this is a planned future feature.

---

### Screen: Session History Sidebar (LABELLED STUB in Phase 1)

**Purpose:** Placeholder for Phase 2 persistent session history.

**Phase 1 appearance:**
- Visible in the sidebar below the multi-file stub.
- Grey, slightly desaturated style.
- Label: "Session history — coming in Phase 2".
- No interactive elements respond to clicks.

---

## Error States

| Situation | User-visible feedback |
|-----------|----------------------|
| File too large (>100 MB) | Toast notification: "File exceeds 100 MB limit." |
| Wrong file type | Toast notification: "Please upload a CSV file." |
| Upload failure (network/server error) | Toast notification: "Upload failed — is the server running?" |
| No file selected when submitting question | Inline validation under the input: "Please select a file first." |
| Agent stream error (`type:"error"` SSE event) | Red agent message bubble with the error text and a "Try again" link that re-fills the input. |
| Server not reachable (fetch fails) | Red agent message bubble: "Cannot reach the server on port 8001. Is it running?" |
| Loading / streaming in progress | Disabled input and button, pulsing "Analysing…" indicator in the chat. |

---

## Tech Stack

The UI tech stack is defined in `spec/architecture.md`. Key choices:
- Next.js 15 static export (`output: 'export'`, `basePath: '/app'`)
- React 19
- Tailwind CSS v4 with PostCSS (`postcss.config.mjs` required)
- `plotly.js` npm package for client-side interactive chart rendering
- `NODE_OPTIONS=--no-experimental-webstorage` in all `package.json` scripts
- `pnpm` for dependency management
