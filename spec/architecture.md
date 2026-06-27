# Architecture

> DataChat: a local, single-user data-analysis chat agent. The headline architectural property is the **privacy boundary** — all computation over the user's data happens locally; only schema + aggregated result tables are ever sent to the LLM. Raw rows never leave the machine.

---

## System Overview

A browser chat UI (Next.js, served as a static export at `/app`) talks to a local FastAPI service. The user uploads a CSV/Excel file; the backend stores it on local disk and profiles it (schema + row count) **without any LLM call**. When the user asks a question, a LangGraph pipeline (1) asks Gemini to translate the question + compact schema + recent chat history into a structured **aggregation plan**, (2) executes that plan **locally** with pandas over the stored file, producing a small result table, and (3) asks Gemini to write a plain-language answer and pick a chart type **from that small aggregate table only**. The answer + chart spec return to the UI, which renders the chart inline. The only LLM-bound payloads are: schema descriptions and small aggregate tables — never raw rows.

## Component Map

```
[Next.js chat UI (frontend/, served at /app)]
        │  multipart upload / chat POST (JSON)
        ▼
[FastAPI routers: datasets, chat]  ──────────────┐
        │                                         │
        ▼                                         ▼
[Aggregation engine (src/data/)]          [LangGraph runner (src/graph/)]
  • storage.py  → ./data/uploads/         plan_aggregation ──► (LLM: Gemini)
  • schema.py   → infer columns/types     run_local_aggregation ──► (NO LLM, local pandas)
  • aggregation.py → pandas groupby/agg   compose_answer_and_pick_chart ──► (LLM: Gemini)
        │                                         │
        ▼                                         ▼
[SQLite metadata store (src/db/)]         [LLMClient → Gemini gemini-2.5-pro]
  Dataset / Conversation / Message              (schema + aggregates ONLY)
        ▲
        │   raw rows live ONLY here:
   ./data/uploads/<dataset>.{csv,xlsx}  ── never read into any LLM prompt
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **UI** (`frontend/`) | Chat interface: upload, message thread, inline chart rendering, labelled stubs. Renders chart specs returned by the API. |
| **API** (`src/api/`) | HTTP contract: `POST /datasets` (upload + profile), `POST /chat` (ask), `GET` retrieval. Validates input, returns the `ok()`/`api_error()` envelope. |
| **Agent graph** (`src/graph/`) | LangGraph pipeline that turns a question into an answer + chart spec. Owns the two LLM calls. See [agent.md](agent.md). |
| **Data engine** (`src/data/`) | **The privacy boundary lives here.** Local file storage, schema inference, and pandas aggregation. The only code that ever touches raw rows; it emits schema + small aggregate tables. |
| **Metadata store** (`src/db/`) | SQLite via SQLAlchemy 2.0: datasets, conversations, messages. No raw row data stored in the DB — only a path reference + schema JSON. |
| **LLM client** (`src/llm/`) | `LLMClient.call_model()` wrapper over the Gemini provider. Every node calls Gemini through this — never the SDK directly. |

## Data Flow

1. **Trigger (upload):** User drops a CSV/`.xlsx` on the UI → `POST /datasets` (multipart). Backend writes the file to `./data/uploads/<uuid>.<ext>`, runs `schema.infer()` over it locally (read with pandas, infer column names/types, count rows), inserts a `Dataset` row (path + schema JSON + row count). Returns dataset id + schema. **No LLM call.**
2. **Trigger (ask):** User types a question → `POST /chat` with `{dataset_id, question, conversation_id?}`.
3. **Plan (LLM):** `plan_aggregation` node sends Gemini the compact schema + the question + recent chat history → receives a structured aggregation plan (group-by columns, metric, aggregation function, optional filter/sort/limit). **Payload = schema + question + history. No raw rows.**
4. **Aggregate (local, NO LLM):** `run_local_aggregation` node loads the file with pandas and executes the plan (`groupby().agg()`), producing a small result table (capped rows). Raw rows stay in the DataFrame in-process and on disk.
5. **Compose (LLM):** `compose_answer_and_pick_chart` node sends Gemini the question + the **small aggregate table** → receives a plain-language answer and a chart spec (`type` + labels + values + title). **Payload = question + aggregate table. No raw rows.**
6. **Output:** `finalize` persists the assistant `Message` (content + chart spec JSON) and returns `{answer, chart}` to the UI, which renders the answer and the chart inline.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`gemini-2.5-pro`) | Plan the aggregation; compose answer + pick chart | Surface a friendly error to the chat; Phase 5 adds retry/backoff + a degraded answer-without-chart path. |
| Local filesystem (`./data/uploads/`) | Stores raw uploaded files (gitignored) | Upload fails with a clear error; existing datasets reference missing files → re-upload prompt. |
| SQLite (`./data/agent.db`) | Metadata: datasets, conversations, messages | Init-on-startup; corruption → recreate via `alembic upgrade head`. |

## Stack

> Generic, every-project rules (model-naming, DB driver, dev port, real-key test rule) live in `harness/patterns/tech-stack.md`. This section is only what **DataChat** picked.

- **Language:** Python 3.11+ (backend), TypeScript/React (frontend).
- **Agent framework:** LangGraph (multi-step pipeline with a conditional error edge; the privacy boundary is enforced by node separation — see [agent.md](agent.md)).
- **LLM provider + model:** Google Gemini, default `gemini-2.5-pro` (env-configurable via `AGENT_LLM_MODEL`; `gemini-2.5-flash` recommended to evaluate for cost — see roadmap Assumed note).
- **Backend:** FastAPI (existing `create_app()` mounts the Next.js export at `/app`).
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (app metadata store; production DB for this app). Alembic for migrations.
- **Frontend:** Next.js 15 + React 19, static export, Tailwind. Recharts for chart rendering.
- **Dependency management:** uv + `pyproject.toml` (Python); pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | (pinned in pyproject) | Agent pipeline orchestration |
| pandas | latest stable | Local CSV/Excel load + groupby/agg (the aggregation engine) |
| openpyxl | latest stable | `.xlsx` reading for pandas |
| fastapi / uvicorn | existing | HTTP service |
| sqlalchemy | 2.0.x | ORM for the metadata store |
| alembic | existing | Schema migrations |
| python-multipart | latest | Multipart file upload parsing for FastAPI |
| google-genai (via existing Gemini provider) | existing | Gemini calls through `LLMClient` |
| recharts | latest stable | Inline bar/line/pie chart rendering in the UI |

**Avoid:**
- **Do NOT send raw data rows to any LLM** — pasting file contents, full-row samples, or `df.head()` into a prompt violates the privacy boundary. Only schema + aggregate tables.
- DuckDB for Phase 1 (pandas is sufficient for single-user, in-memory scope; revisit only if file sizes outgrow memory).
- Calling the Gemini SDK directly from nodes — always go through `LLMClient.call_model()`.
- A second/duplicate `src/agent/` package — this repo's layout is **flat under `src/`** (bare imports like `from graph.state import AgentState`). Extend in place.
- Heavy charting libs (D3 from scratch, Plotly) — Recharts covers bar/line/pie simply.

## Deployment Model

Local long-running uvicorn service on port 8001 (single process, single user). Frontend is built to a static export (`cd frontend && pnpm build` → `frontend/out/`) and served by the same FastAPI app at `http://localhost:8001/app/`. Raw uploads live under `./data/uploads/` (gitignored); metadata in `./data/agent.db`.
