# UI

## UI Type

Web application — a single-page chat interface with a persistent sidebar for dataset management.

## Layout

The application is a two-panel layout:

```
+--------------------+------------------------------------------+
|  Dataset Sidebar   |           Chat Panel                     |
|                    |                                          |
|  [Upload button]   |  [Conversation history — scrollable]     |
|                    |                                          |
|  Datasets:         |  User: "Which customers placed >3..."    |
|  - sales_data      |  Agent: [Table: customer | order_count]  |
|    (1500 rows)     |         [SQL: SELECT customer... ▼]      |
|  - products        |                                          |
|    (200 rows)      |  [Chat input bar]                        |
+--------------------+------------------------------------------+
```

---

## Views / Screens

### Screen: Main Application

**Purpose:** The only screen in Phase 1. Combines dataset management and chat interaction in one view.

**Key elements:**

**Dataset Sidebar (left panel):**
- "Upload Dataset" button — opens the file picker (accepts `.csv` and `.json` only)
- Upload progress indicator — shown while the file is being uploaded and parsed; disappears on completion or error
- Dataset list — each entry shows: dataset name (derived from file name), row count, and a column-count badge
- Hovering a dataset entry shows a tooltip with the full column list and inferred types
- Empty state: "No datasets yet. Upload a CSV or JSON file to get started."

**Chat Panel (right panel):**
- Conversation history — a scrollable list of turns, newest at the bottom; auto-scrolls on new content
- Each **user turn** shows the question text, aligned right, with a timestamp
- Each **assistant turn** shows:
  - A result table (see Table Component below) if the query succeeded
  - An error message if the query failed, with the specific error code in small text
  - A collapsible "View SQL" toggle that reveals the generated SQL statement when expanded
  - A "Returned N rows" summary line beneath the table (or "Results truncated to 1 000 of N total rows" when truncated)
- Empty state: "Upload a dataset to start asking questions."
- Chat input bar — fixed at the bottom of the chat panel; a single text field and a "Send" button; disabled until at least one dataset is loaded; pressing Enter or clicking Send submits the question

**Table Component:**
- Renders query results as an HTML table with column headers
- Paginated client-side: 25 rows per page, with Previous / Next controls and a "Page X of Y" indicator
- Column headers are non-interactive in Phase 1 (no sorting or filtering)
- Numeric values are right-aligned; text values are left-aligned

---

### Screen: Stub / Offline Banner

**Purpose:** Display a visible warning when the Gemini API key is not configured, so the user knows NL queries will not work.

**Key elements:**
- A full-width banner at the top of the page with a warning-level colour (amber/yellow)
- Text: "Gemini API key not configured. Set the GEMINI_API_KEY environment variable and restart the server to enable natural-language queries."
- The banner is present on every page load when the key is absent; it disappears automatically when the key is present (no user action required)

---

## Error States

| Situation | UI Behaviour |
|-----------|-------------|
| File too large (>50 MB) | Inline error below the upload button: "File exceeds the 50 MB limit." |
| Unsupported file format | Inline error: "Only .csv and .json files are supported." |
| Upload server error | Inline error: "Upload failed. Please try again." |
| LLM unavailable (502) | Chat turn shows: "Could not reach the AI service. Please try again in a moment." |
| SQL rejected (422) | Chat turn shows: "The AI returned an unsafe query. Try rephrasing your question." |
| Unknown table (422) | Chat turn shows: "The query referenced a table that isn't in your session. Please re-upload the dataset." |
| Query timeout (504) | Chat turn shows: "The query took too long to run. Try a more specific question." |
| Session load failure | Full-page error: "Could not load your session. Refresh to start a new one." |
| No datasets when submitting | Chat input bar is disabled; tooltip on hover: "Upload a dataset first." |

## Interaction Rules

- The chat input is disabled while a query is in flight; a loading spinner replaces the Send button during this time.
- Uploading a new dataset does not clear the conversation history.
- The page does not require a full reload to pick up a newly uploaded dataset; the sidebar updates immediately on successful upload.
- On page load the UI calls `GET /api/sessions/current`; if the session has existing datasets and conversation history, they are rendered before the user types anything.
