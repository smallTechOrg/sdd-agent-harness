# Architecture

## System Overview

The Data Analysis Agent is a single-process web application running locally on the user's machine. A FastAPI server handles all HTTP traffic: file uploads, analysis requests, history queries, and serving the compiled Next.js frontend as static files under `/app`. The user interacts entirely through the browser. The only external network call is to the Gemini API, and only when the user submits a free-text NL question — uploaded file data never leaves the machine.

## Component Map

```
Browser (Next.js static export at /app)
    │
    │  POST /uploads   GET /uploads
    │  POST /analyses  GET /analyses/{id}
    │  GET /health
    ▼
FastAPI server (port 8001)
    │
    ├── Upload handler ──────────► Local filesystem  (data/uploads/<uuid>.<ext>)
    │                              SQLite DB          (uploads table)
    │
    └── Analysis runner ─────────► LangGraph graph
                                       │
                                       ├── parse_upload       (read file → DataFrame)
                                       ├── route_analysis     (preset vs. nl_query)
                                       │
                                       ├── [preset branch]
                                       │     run_preset_analysis  (pandas — no LLM)
                                       │
                                       └── [nl_query branch]
                                             run_nl_query     (Gemini API call)
                                             reflect_nl_result (Phase 4+ retry/reflection)
                                       │
                                       ├── format_response    (build AnalysisResult)
                                       ├── handle_error       (capture error)
                                       └── finalize           (persist, return)
                                       │
                                       SQLite DB          (analyses table)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (Next.js) | Upload form, analysis controls, results display (summary card + Plotly chart + table) |
| API (FastAPI) | HTTP routing, request validation, response envelope, file save |
| Agent graph (LangGraph) | Stateful analysis pipeline: parse → route → analyze → format → finalize |
| Domain logic (pandas) | All preset analyses — no LLM involved |
| LLM integration (Gemini) | NL query only: generate pandas code from question + schema |
| Storage (SQLite) | Upload metadata, analysis results, run history |
| File storage (local FS) | Raw uploaded files at `data/uploads/` |

## Data Flow

1. **Upload trigger:** user drops or picks a file in the browser; browser POSTs multipart to `POST /uploads`.
2. FastAPI saves the file to `data/uploads/<uuid>.<ext>`, reads column headers and row count via pandas, inserts an `UploadRow`, and returns `{ upload_id, filename, row_count, col_count, columns }`.
3. **Analysis trigger:** user selects analysis type + parameters and clicks Run; browser POSTs `{ upload_id, analysis_type, params }` to `POST /analyses`.
4. FastAPI inserts a pending `AnalysisRow` and calls `run_analysis(upload_id, analysis_type, params)` — a synchronous LangGraph invocation.
5. `parse_upload` reads the file from disk into a pandas DataFrame.
6. `route_analysis` reads `analysis_type`; conditionally routes to the preset branch or the NL query branch.
7. **Preset branch:** `run_preset_analysis` runs the selected pandas operation and builds `{ summary, chart_json, table }` with no LLM call.
8. **NL query branch (Phase 3+):** `run_nl_query` builds a Gemini prompt from the DataFrame schema + up to 20 sample rows + the user question; calls Gemini; extracts generated pandas code; executes it in a sandboxed namespace; formats the result.
9. `format_response` normalizes the result into `{ summary: str, chart_json: str|null, table: list|null }`.
10. `handle_error` (on any exception) captures the error message; `finalize` writes the result back to `AnalysisRow`.
11. FastAPI returns `{ data: { analysis_id, status, summary, chart_json, table }, error: null }`.
12. Browser renders: Plotly chart from `chart_json` (client-side via plotly.js), plain-English summary card, paginated table.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`gemini-2.5-pro`) | NL query: generate pandas code from question | `run_nl_query` sets error in state; `handle_error` returns a user-visible error message; no crash |
| Local filesystem | Store uploaded files | Upload fails with a 500 error; no data loss for previously uploaded files |
| SQLite (local file) | Upload history + analysis results | Startup failure if `data/` directory not writable; surfaced at startup |

## Stack

> This project's concrete technology choices. Generic rules live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12+
- **Agent framework:** LangGraph `>=0.1` (existing in skeleton; multi-node conditional routing pattern)
- **LLM provider + model:** Google Gemini / `gemini-2.5-pro` (env: `AGENT_LLM_MODEL`; client already wired in `src/llm/providers/gemini.py`)
- **Backend:** FastAPI `>=0.115` (existing skeleton)
- **Database + ORM:** SQLite (`sqlite:///./data/agent.db`) + SQLAlchemy `>=2.0` sync (existing pattern)
- **Migrations:** Alembic (existing; new migration `0002_data_analysis.py`)
- **Frontend:** Next.js 15 + React 19 (existing skeleton; static export at `frontend/out/`, served by FastAPI at `/app`)
- **Frontend styling:** Tailwind v4 (existing; `postcss.config.mjs` + `@source "../"` required — must not be overwritten)
- **Dependency management:** uv + `pyproject.toml` (Python) / pnpm (frontend)

| Key library | Version constraint | Purpose |
|-------------|-------------------|---------|
| pandas | `>=2.2` | All data parsing, preset analyses, NL code execution namespace |
| openpyxl | `>=3.1` | pandas Excel (.xlsx/.xls) read support |
| plotly | `>=5.22` | Server-side chart JSON generation |
| plotly.js-dist-min | npm `>=2.30` | Client-side chart rendering from JSON |
| python-multipart | `>=0.0.9` | FastAPI multipart file upload parsing |
| langgraph | `>=0.1` (existing) | Agent graph orchestration |
| google-genai | `>=2.9.0` (existing) | Gemini API client |
| sqlalchemy | `>=2.0` (existing) | ORM + sync session |
| alembic | `>=1.13` (existing) | DB migrations |
| fastapi | `>=0.115` (existing) | HTTP server |
| pydantic | `>=2.7` (existing) | Request/response models |
| pydantic-settings | `>=2.3` (existing) | Settings with `extra="ignore"` |

**Avoid:**
- Sending uploaded file bytes to any external API (data locality constraint).
- Calling Gemini on any preset analysis path (cost constraint; presets are always pure pandas).
- AsyncIO for database operations — the existing skeleton uses synchronous SQLAlchemy; keep it consistent.
- Replacing or overwriting `postcss.config.mjs` or the `@source` line in `globals.css` — Tailwind v4 build breaks without them.

## Deployment Model

Single-process local server. Run with `uv run python -m src` from the project root. The frontend must be pre-built (`cd frontend && pnpm build`) to generate `frontend/out/` which FastAPI serves at `/app`. No containerization, no cloud deployment — fully local.

> **Assumed:** pandas, openpyxl, plotly, and python-multipart are not yet in `pyproject.toml` and will be added in Phase 1 as `[project.dependencies]`. The `plotly.js-dist-min` npm package will be added to `frontend/package.json` in Phase 1.

> **Assumed:** The existing `RunRow` model and `/runs` endpoints remain untouched for backwards compatibility. New `UploadRow` and `AnalysisRow` models are added to `src/db/models.py` with a new Alembic migration `0002_data_analysis.py`.

> **Assumed:** The LangGraph graph in `src/graph/` is rebuilt in Phase 1 to serve the data analysis pipeline. The boilerplate `transform_text` node is replaced. The graph module path (`src/graph/agent.py`, `src/graph/nodes.py`, etc.) stays the same.
