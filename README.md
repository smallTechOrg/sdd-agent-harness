# Local Data Analyst

> **All commands run from the repo root.** The repo root *is* the project — there is no subdirectory to `cd` into (except the one frontend block, which says so explicitly). Every Python command is prefixed with `uv run`; bare `alembic` / `pytest` / `python` will fail unless you have manually activated the venv.

A personal, locally-run data-analysis agent. Upload a CSV, get an automatic profile, then ask natural-language questions and receive a plain-English answer with the key numbers called out, ONE auto-picked chart, a compact summary table, and a collapsible "show its work" panel (the plan, the step trace, and the exact DuckDB SQL that ran). All raw data stays on your machine — the agent generates DuckDB SQL that runs **locally**, and only column schemas and small aggregate results are ever sent to the LLM.

This is **Phase 1** — the smallest first-time-right win: upload → profile → ask ONE question → answer. Everything coming in later phases is shipped as a clearly-labelled, non-functional stub so you can see where the product is going.

---

## Privacy Boundary (plainly stated)

**Raw data rows never leave your machine.** DuckDB holds and queries the full dataset locally; the full result table renders in your browser. The LLM (Gemini) only ever receives (a) the column **schema** — names + DuckDB types + a tiny health summary — and (b) small, bounded **aggregate** results used to phrase the answer. A named `privacy_guard` step is the single chokepoint that enforces this, and every LLM input is logged so the property is auditable.

---

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package + runner)
- [`pnpm`](https://pnpm.io/) (frontend package manager)
- Python 3.11+
- A `.env` file with a Gemini API key. Copy the example and fill the key:

```bash
# from the repo root
cp .env.example .env
# then edit .env and set:
#   AGENT_GEMINI_API_KEY=<your Gemini API key>
```

> `AGENT_LLM_MODEL` defaults to `gemini-3.1-pro-preview` and **does not need to be set** — the app works out of the box with only the key filled in. (`gemini-3.1-pro-preview` is the ID the live Gemini API serves for the gemini-3.1-pro family.)

---

## Setup & Run

All commands run from the **repo root** unless a block says otherwise.

### 1. Install Python dependencies

```bash
# repo root
uv sync --extra dev
```

(`--extra dev` includes the test dependencies. Use `uv sync` if you only want to run the app.)

### 2. Apply database migrations and verify

```bash
# repo root
uv run alembic upgrade head
uv run alembic current
```

`uv run alembic current` must print a revision — for Phase 1 it shows:

```
0002 (head)
```

Blank output means no migration was applied — re-run `uv run alembic upgrade head`.

### 3. Build the frontend

```bash
# from the frontend directory
cd frontend && pnpm install && pnpm build
cd ..
```

This produces the static export the backend serves at `/app/`.

### 4. Start the server

```bash
# repo root
uv run python -m src
```

Then open **`http://localhost:8001/app/`** in your browser.

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | The Local Data Analyst UI |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

---

## Using It (the Phase-1 capability)

1. **Upload a CSV** (e.g. sales by region/month). The agent auto-profiles it: row count, each column's name + inferred type, and a null/health summary — within ~30s. (No LLM call on upload.)
2. **Ask a natural-language question**, e.g. *"Which region had the highest total sales?"* You get back, within ~30s:
   - a plain-English **answer** with the key numbers called out,
   - ONE **auto-picked chart** (bar / line / pie, chosen by a deterministic heuristic),
   - a compact **summary table**,
   - the **per-question cost** (computed from real Gemini token usage).
3. **Expand "Show its work"** to see the plan, the step trace (any failed-then-retried SQL is shown), and the **exact DuckDB SQL** that ran. The generated SQL is dialect-safe DuckDB, and a SQL error is never a dead end — the agent feeds the error back and regenerates corrected SQL (bounded retries), with the retry visible in the trace.

Throughout, **raw rows are never sent to the LLM** — only the schema + bounded aggregates. Every run is persisted to SQLite tied to its dataset (plan, SQL, trace, result summary, chart, cost). You can now **revisit past datasets and re-open prior question runs from the sidebar** — the browser is persisted across restarts and re-opening a run is a pure DB read (no LLM call).

### API routes

| Method & path | Purpose |
|---------------|---------|
| `POST /datasets` | Upload a CSV (multipart `file` field); ingest into local DuckDB and profile it. No LLM call. |
| `GET /datasets` | List all datasets newest-first for the sidebar (with `question_count`). No LLM call. |
| `GET /datasets/{id}` | Fetch a dataset's profile (re-open the profile card). |
| `GET /datasets/{id}/runs` | Question/run history for a dataset, newest-first, each reconstructed to the live answer shape. No LLM call (pure DB read). |
| `POST /datasets/{id}/ask` | Ask a natural-language question; run the agent and return the answer + chart + summary table + show-its-work trace. |

Responses use the envelope `{"data": <payload>, "error": null}` on success; failures return an HTTP error with `{"detail": {"code": ..., "message": ...}}` (an *agent* failure — e.g. SQL uncorrectable after retries — returns HTTP 200 with `status="failed"` and the trace in the body so the UI can render what was tried). See [`spec/api.md`](spec/api.md) for the full contract.

---

## Coming in Later Phases (clearly-labelled stubs)

These appear in the Phase-1 UI as greyed / "coming soon" affordances — they are visible but not yet functional:

- **Conversation follow-ups** — the "follow-up question" box and "suggested questions" chips are stubs (Phase 3 / Phase 6).
- **Multi-file JOIN / compare** — the "compare another file" button is a stub (Phase 4).
- **Excel upload + column notes** — the uploader accepts `.csv` only; an "Excel — coming soon" note and the "column notes" panel are stubs (Phase 5).
- **Suggested follow-ups / clarifying-question gate / running daily-cost tally** — the daily-cost figure shows "—" for now; per-question cost IS real (Phase 6).

---

## Tests

### Python tests (real Gemini via `.env`)

```bash
# repo root — requires AGENT_GEMINI_API_KEY in .env
uv run pytest
```

Integration tests call the real Gemini API and run against the real DuckDB + SQLite drivers.

### Frontend end-to-end (Playwright)

```bash
# from the frontend directory, with the app built (and the backend running for the live smoke)
cd frontend && pnpm exec playwright test
cd ..
```

---

## Repo Layout (Phase 1)

```
src/
  api/         ← FastAPI routers: create_app, health, datasets (upload / get / ask)
  analysis/    ← DuckDB engine: CSV ingest, schema, profile, dialect-safe local SQL, chart heuristic
  graph/       ← LangGraph pipeline: plan → privacy_guard → generate_sql → execute_sql → retry → phrase_answer → pick_chart → finalize
  db/          ← SQLAlchemy models (datasets, question_runs) + session
  domain/      ← Pydantic request/response models
  llm/         ← LLMClient + GeminiProvider (default gemini-3.1-pro-preview)
  prompts/     ← plan.md, generate_sql.md, phrase_answer.md
  observability/
frontend/      ← Next.js static export, served by FastAPI at /app/
tests/
  unit/        ← passes with no API key
  integration/ ← requires real key in .env
spec/          ← roadmap, architecture, capabilities/, data, api, ui, agent
pyproject.toml
alembic.ini    ← Alembic migrations (alembic/)
.env.example
```
