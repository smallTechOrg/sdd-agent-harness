# Vision

## What This Agent Does

The Data Analyst Agent lets a non-technical user upload CSV or JSON datasets, ask questions about those datasets in plain English via a chat interface, and receive the answers as formatted data tables — all without writing a single line of SQL. The agent translates each natural-language question into a SQL query, executes it against the uploaded data, and streams the result back into the conversation.

## Who Uses It

**Data analysts and business users** who have datasets (exports, reports, log files) they want to explore quickly without a dedicated BI tool or SQL skills. They open the web app, upload one or more files, and ask questions ("Which customers placed more than 3 orders last month?") to get answers in seconds.

## Core Problem Being Solved

Exploring a dataset today requires either writing SQL by hand, importing data into a heavyweight BI tool, or asking a technical colleague. This agent eliminates that friction: the user uploads a file and asks questions in natural language, receiving structured answers immediately. The manual step of writing and debugging SQL is replaced by a single chat turn.

## Success Criteria

- [ ] A user can upload a CSV or JSON file and receive confirmation that the dataset is ready to query within 5 seconds for files up to 50 MB.
- [ ] A natural-language question produces a SQL query and a formatted table result within 10 seconds end-to-end (excluding network latency to the LLM provider).
- [ ] Query results are displayed as a paginated table in the web UI; the raw SQL is visible on demand.
- [ ] A user who closes and reopens the browser tab within 24 hours resumes the same session with full dataset and conversation history intact.
- [ ] Every SQL statement executed is written to the audit log with timestamp, session ID, originating question, and row count returned.
- [ ] The system sends only the dataset schema (column names and types) — not row data — to the LLM on every query turn.

## What This Agent Does NOT Do (Out of Scope)

- No charts, graphs, or visualisations of any kind (Phase 2).
- No dashboards or saved report views (Phase 2).
- No multi-step analytical reasoning or plan-then-execute agent loops (Phase 2).
- No cloud storage: all uploaded data stays on the server's local filesystem.
- No user authentication or multi-tenant access control — single-user deployment only.
- No scheduled queries or automated report delivery.
- No data editing, insertion, or deletion via the chat interface.
- No support for database connections (Postgres, MySQL, etc.) — file upload only.

## Key Constraints

- The Gemini API key is supplied by the operator as the environment variable `GEMINI_API_KEY`; it must never be exposed to the client. When the key is absent the system starts in degraded mode: the NL-query capability is unavailable and the UI displays a warning banner (see `spec/ui.md`).
- Token economy: the LLM receives the schema of relevant tables and the user's question — never raw row data.
- All uploaded data is stored locally; no file is sent to any external service other than the schema excerpt sent to Gemini.
- Single-user, single-server deployment; no horizontal scaling requirement for Phase 1.
- Maximum supported upload file size: 50 MB per file.

## Future Phases

| Phase | Description | Success Gate |
|-------|-------------|--------------|
| 1 | Dataset upload, NL-to-SQL, query execution, formatted table responses, persistent sessions, audit log | All Phase 1 success criteria above pass; end-to-end smoke test green |
| 2 | Charts and visualisations (Plotly/Chart.js) embedded in chat responses | A bar chart renders correctly for a numeric query result |
| 3 | Dashboards — pinnable query results with auto-refresh | A saved dashboard with 3 panels loads and refreshes on demand |
| 4 | Senior analyst simulation — multi-step reasoning, automatic sub-query decomposition | Agent correctly decomposes a 3-step analytical question into sub-queries and synthesises a final answer |
