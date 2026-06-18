# Vision

## What This Agent Does

DataChat is a browser-based web application that lets users upload a CSV or JSON data file and then ask plain-English questions about it. A ReAct agent powered by Google Gemini reads the uploaded data, generates pandas operations, executes them against the actual dataset, observes the results, and loops until it can return a definitive answer. The answer is returned with a short reasoning trace so the user can see how it was derived. Users can ask multiple follow-up questions within a session without re-uploading their file.

## Who Uses It

**Primary user:** A non-technical or semi-technical analyst, researcher, or business stakeholder who has a data file and wants quick answers without writing code. They can use a chat interface but do not want to run Python or SQL themselves.

Their goal: upload a file once, ask several questions ("What is the average sales by region?", "Which product had the highest return rate?"), and get accurate, grounded answers in seconds.

## Core Problem Being Solved

Extracting insights from a CSV or JSON file today requires writing code (Python/pandas, SQL) or importing data into a BI tool — both require technical skill and setup time. DataChat removes that barrier: the user uploads a file, types a question in plain English, and gets a grounded answer backed by actual pandas execution against their data. The agent does not hallucinate numbers — it runs real computations and shows its work.

## Success Criteria

- [ ] A user can upload a CSV or JSON file (up to 50 MB) and receive confirmation that it was parsed successfully within 5 seconds.
- [ ] A user can ask a factual question about their data (e.g., "What is the max value in column X?") and receive a correct answer grounded in the actual data within 30 seconds.
- [ ] The agent shows a reasoning trace — each action it took and the result — alongside the final answer.
- [ ] When no Gemini API key is set, the app runs in stub mode with a visible banner on every page.
- [ ] All 12+ tests pass with no API key required (stub mode).

## What This Agent Does NOT Do (Out of Scope for v0.1)

- No chart or visualization output (deferred)
- No multi-dataset joins or cross-file queries (deferred)
- No saved query history across browser sessions (deferred)
- No authentication or multi-user isolation (deferred)
- No streaming token output (deferred)

## Key Constraints

- LLM: Google Gemini only (`google.genai` SDK, model `gemini-2.5-flash`)
- Database: SQLite (file-based, no external DB required)
- Agent actions: pandas operations only, executed via a frozenset allowlist — never raw `eval`
- Max file size: 50 MB
- Max ReAct iterations: 10

## Phases of Development

| Phase | Description | Success Gate |
|-------|-------------|--------------|
| Phase 1 | Domain models + DB schema + alembic | `uv run pytest` — 10/10 unit tests pass |
| Phase 2 | ReAct agent loop + FastAPI API + golden-path smoke test + README | `uv run pytest` — 12/12 tests pass; live-server check green |

## Future Phases

- Phase 3: Real Gemini integration with eval tests against a sample dataset
- Phase 4: Chart output (Plotly)
- Phase 5: Query history UI
- Phase 6: Streaming token output
