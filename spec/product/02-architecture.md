# Architecture

## System Overview

DataChat is a single-process Python application. The user's browser talks to a FastAPI server that hosts both the React frontend (as a static SPA) and the REST API. On the backend, an LangGraph ReAct agent receives the user's question, loads the in-memory DataFrame for the session, iteratively generates and executes pandas operations against the real data, and returns a grounded answer with a full action trace.

## Component Map

```
Browser (React SPA)
    ↓ POST /api/sessions          (upload file)
    ↓ POST /api/sessions/{id}/messages  (ask question)
FastAPI server (src/datachat/)
    ↓
LangGraph ReAct agent (graph/)
    ↓ tools/pandas_executor.py    (sandboxed pandas ops)
    ↓ llm/providers/              (Gemini or stub)
SQLite DB (datachat.db via SQLAlchemy 2.0 + Alembic)
```

## Data Flow

1. User uploads CSV/JSON → server parses into a pandas DataFrame stored in a module-level dict keyed by `session_id` → metadata (row count, column names) persisted to `sessions` table.
2. User posts a question → API creates a `RunRow` → calls `run_agent(session_id, question)`.
3. Agent runs `setup` (load DataFrame), then loops: `plan_action` (LLM returns next pandas op or `FINAL ANSWER:`) → `execute_action` (run op, append result to `action_history`) → back to `plan_action`.
4. On `FINAL ANSWER:` or max-iterations, agent runs `finalize` / `force_finalize` → updates RunRow to `completed` / `force_completed` → API returns answer + reasoning trace.
5. User and assistant messages persisted to `messages` table.

## Tech Stack

- **Language:** Python 3.12
- **Web framework:** FastAPI 0.115+
- **Agent framework:** LangGraph 0.2+
- **LLM:** Google Gemini via `google-genai` (NOT deprecated `google.generativeai`)
- **Default model:** `gemini-2.5-flash`
- **Data processing:** pandas 2.x
- **Database:** SQLite via SQLAlchemy 2.0 + Alembic
- **Frontend:** React + TypeScript (Vite) served from FastAPI dist/ (Phase 2 uses a minimal HTML fallback; full React UI in Phase 3)
- **Package manager:** uv
- **Testing:** pytest + FastAPI TestClient
