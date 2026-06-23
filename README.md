# Data Analysis Agent

Upload a CSV file and ask questions about your data in plain English. Powered by Google Gemini + LangGraph, with a Model Context Protocol (MCP) tool layer: each uploaded file becomes an in-process MCP server that answers `run_query` calls with DuckDB over Parquet.

> **All commands run from the repo root.**

---

## Quick Start

### 1. Install dependencies

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set DATAANALYSIS_GEMINI_API_KEY to your Gemini API key
# Leave it blank to run in stub mode (offline, no real AI)
```

### 3. Apply database migrations

```bash
uv run alembic upgrade head
uv run alembic current   # must print a revision hash — blank means migration failed
```

### 4. Run the app

```bash
uv run python -m data_analysis_agent
```

Open [http://localhost:8001](http://localhost:8001) in your browser.

---

## Features (v0.1)

- **CSV Upload** — upload any CSV file via the web form
- **Natural Language Q&A** — type a question, get a plain-text answer from Gemini
- **Query History** — review past questions and answers per dataset

---

## Stub Mode

If `DATAANALYSIS_GEMINI_API_KEY` is not set, the app runs in **stub mode**:
- A yellow banner appears on every page
- Answers are placeholder text (not real AI output)
- No API calls are made — safe for offline development

---

## Running Tests

```bash
uv run pytest
```

All tests pass with no Gemini API key required (stub mode exercises the full MCP + DuckDB pipeline).

---

## Project Structure

```
src/data_analysis_agent/
├── api/          ← FastAPI routes
├── config/       ← Settings (pydantic-settings)
├── db/           ← SQLAlchemy models + session
├── domain/       ← Pydantic domain models
├── graph/        ← LangGraph pipeline (state, nodes, edges, runner)
│   ├── mcp_pool.py  ← MCP client pool (the only importer of mcp.shared.memory)
│   └── mcp/          ← per-source in-process MCP servers (csv_server: DuckDB over Parquet)
├── llm/          ← Gemini + stub provider
├── tools/        ← CSV→Parquet ingestion, table naming, LLM-generated descriptions
└── templates/    ← Jinja2 HTML templates

tests/
├── unit/         ← Pure unit tests (no DB, no network)
└── integration/  ← End-to-end pipeline + golden-path UI tests
```

---

## Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.12 |
| Web framework | FastAPI + uvicorn |
| UI | Jinja2 templates (React/Vite in Phase 4) |
| Agent | LangGraph (async nodes) |
| Tool protocol | Model Context Protocol — official `mcp` SDK 1.28.0 (in-process FastMCP per source) |
| Data query engine | DuckDB (read-only, over Parquet) |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| Metadata DB | SQLite + SQLAlchemy 2.0 |
| Migrations | Alembic |

---

## Deferred (Future Phases)

- Charts and visualizations (Phase 4)
- AI-written insights / dataset summaries (Phase 5)
- React/Vite frontend (Phase 4)
- Multi-dataset management (Phase 6)
- User authentication (Phase 7)
