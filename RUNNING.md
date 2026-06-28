# Pandora — Running the Private CSV Analysis Agent

> **All commands run from the repo root** (where `pyproject.toml` and `alembic.ini` live). There is no subdirectory to `cd` into except the one-time frontend build. Every Python command is prefixed with `uv run`.

Pandora is a private, single-user CSV/Excel analysis agent. Upload a spreadsheet, ask plain-language questions; it writes and runs **real pandas locally** (sandboxed) on the full dataset and returns a plain-language answer, an interactive chart, a summary table, the exact runnable code, and the per-question + daily cost. **Raw data rows never leave the machine** — only schema, column metadata, and computed aggregates are sent to the LLM (Gemini).

> **Platform:** a local POSIX machine (macOS or Linux). The sandbox uses `resource.setrlimit` + subprocess isolation (no Docker).

## One-time setup

1. Copy `.env.example` to `.env` and set your Gemini key:
   ```
   AGENT_GEMINI_API_KEY=<your key>
   ```
   (`.env` is the only manual step. The database URL defaults to `sqlite:///./data/agent.db`.)

2. Install Python deps and create the database schema:
   ```
   uv sync
   uv run alembic upgrade head
   uv run alembic current      # must print: 0001 (head)  — NOT blank
   ```

3. Build the frontend (produces `frontend/out/`, served by the backend at `/app/`):
   ```
   cd frontend && pnpm install && pnpm build && cd ..
   ```

## Run

```
uv run python -m src
```
Then open **http://localhost:8001/app/** in a browser.

## Use it (Phase 1)

1. Upload a CSV or `.xlsx`. A sample ships at `examples/sales.csv`.
2. The profile card appears: rows/columns, per-column type, missing %, ranges, distinct counts, plus 2–3 suggested questions and any data-quality flags.
3. Type a question (or click a suggestion), e.g. *"What is total revenue by region?"*. A live step list shows Generating code → Running code → Summarising with a step counter and elapsed timer.
4. The answer appears: plain-language text, an interactive chart, a summary table, a collapsible **Show code & steps** panel with the copy-runnable pandas, and a cost line (this question's tokens + cost, and today's running total).

Features badged **Phase 2 / 3 / 4** (History, follow-up conversation, multi-file/join, deep analysis) are visible but disabled — planned, not broken.

## Tests

```
uv run pytest -q                                   # full backend suite (real Gemini key from .env)
cd frontend && npx playwright test tests/e2e/      # E2E — requires the server running on :8001
```

The suite includes a privacy-boundary test (no raw row ever reaches the LLM), sandbox-security tests (network blocked, timeout + memory enforced, filesystem restricted), and a 50,000-row full-dataset correctness test.
