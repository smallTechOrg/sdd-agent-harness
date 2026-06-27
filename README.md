# DataChat

**Upload a CSV, ask a plain-English question, get a plain-English answer plus a bar chart — all on your own machine.**

DataChat is a personal, local data-analysis agent. Your raw data never leaves your computer: only the table *schema* and small *computed aggregates* are ever sent to the LLM. Every row-level calculation runs locally in DuckDB.

> **All commands run from the repo root.** Every command in this README assumes your shell is in the root of this repository (the repo root *is* the project).

---

## The privacy promise (the whole point)

Your raw data rows **never** leave your machine.

- The CSV you upload is loaded into a **local DuckDB** database.
- All filtering, grouping, and aggregation happens **locally**, in DuckDB.
- Only two things are ever sent to Gemini: (1) the column names/types (the *schema*), and (2) the small *aggregated result* of a computation (e.g. "sum of revenue by region").
- This is enforced in code by `assert_no_raw_rows(...)` in `src/tools/compute.py`, which is called by the only two graph nodes that talk to the LLM. If raw rows ever tried to leak, the call fails.
- It is proven by `tests/phase1/test_privacy_boundary.py`.

---

## Quickstart

```bash
cp .env.example .env
# edit .env and set your Gemini key:
#   AGENT_GEMINI_API_KEY=<your key>
uv sync
python agent.py --run
```

Then open **http://localhost:8001/app/** and:

1. Upload a CSV.
2. Ask a question in plain English (e.g. *"What were total sales by month?"*).
3. Read the answer and see the bar chart.

`python agent.py --run` applies database migrations, builds the frontend, and starts the server on port **8001** for you — no separate steps required.

To verify your setup **without** starting the server:

```bash
python agent.py        # checks tools, .env, deps, and runs unit tests
```

---

## How it works

DataChat is a small agent graph:

```
profile_data → plan_compute → execute_local → phrase_answer → finalize
                                                          └→ handle_error
```

- **profile_data** — inspects the uploaded CSV's schema locally.
- **plan_compute** *(LLM)* — given only the schema + your question, plans a local aggregation.
- **execute_local** — runs that aggregation in DuckDB, on your machine.
- **phrase_answer** *(LLM)* — given only the small aggregated result, writes a plain-English answer and a chart spec.
- **finalize / handle_error** — returns the result or a clean error.

Only `plan_compute` and `phrase_answer` call the LLM, and both pass their payload through `assert_no_raw_rows(...)` first. DataChat is frugal — at most **2 LLM calls** per question.

**Stack:** FastAPI + LangGraph + Gemini 2.5 Flash (`gemini-2.5-flash`) + DuckDB (local analysis) + SQLite (app metadata) + Next.js (static export).

---

## The database & manual steps

There are two databases, and they hold different things:

- **SQLite** at `./data/agent.db` — the app's own metadata store (datasets, questions). This is **not** your analysed data.
- **DuckDB** (local) — where your uploaded CSV rows actually live and are computed on.

`python agent.py --run` applies migrations automatically. To run and verify them yourself:

```bash
uv run alembic upgrade head    # create/upgrade the SQLite metadata tables
uv run alembic current         # verify — should print: 0002 (head)
```

If `uv run alembic current` shows `0002 (head)`, your metadata tables are in place.

### Building the frontend manually (optional)

`python agent.py --run` builds the frontend for you. To build it by hand (requires Node 20+ and pnpm):

```bash
cd frontend && pnpm install && pnpm build
```

This produces `frontend/out/`, which the API serves at `/app/`.

---

## URLs (once running)

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | The DataChat UI — upload, chat, chart |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

---

## API endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/datasets` | multipart form, field `file` (a CSV) | `{ dataset_id, name, row_count, columns }` |
| `POST` | `/ask` | JSON `{ dataset_id, question }` | `{ question_id, answer_text, chart_spec, status }` |
| `GET` | `/health` | — | health status |

---

## Running tests

Tests run against the **real** Gemini model using `AGENT_GEMINI_API_KEY` from `.env`.

**Phase 1 gate** (the command that defines "done" for this build — 32 tests):

```bash
uv run alembic upgrade head && uv run pytest tests/phase1 -q
```

Other test runs:

```bash
uv run pytest tests/unit/ -q    # fast, no / limited LLM use (15 tests)
uv run pytest -q                # whole suite (49 tests)
```

---

## Roadmap

**Phase 1 — done (this build):** upload a CSV → ask a question → get an answer + bar chart, with the privacy boundary enforced and proven.

Coming next:

- **Phase 2** — connect a PostgreSQL database as a data source.
- **Phase 3** — richer charts + a downloadable report.
- **Phase 4** — agentic upgrade and resilience (memory, reflection, guardrails).
- **Phase 5** — complete system + anomaly detection.

The UI shows clearly-labelled **"Coming soon"** stubs for *Connect PostgreSQL*, *Switch dataset*, *Download report*, and *Detect anomalies*. These are intentional previews of upcoming phases — **not** bugs.

---

## Stack

FastAPI · LangGraph · Gemini 2.5 Flash · DuckDB (local row-level compute) · SQLite (app metadata) · Next.js · Alembic · `uv`.
