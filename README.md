# Data Analysis Agent

> **All commands below run from the repo root** (the directory containing `pyproject.toml`, `alembic.ini`, and this README). There is no subdirectory to `cd` into except the one-time `frontend` build step, which returns you to the root.

Upload a spreadsheet and ask questions about it in plain English. The agent computes the **real** answer over your **actual** data — it never guesses a number — and shows you the plain-language answer, the exact pandas code it ran, and the captured output of running that code. Your raw data stays on your machine: only the column schema and a small sample are ever sent to the LLM.

---

## What It Does

You open the web app, drop in a CSV, and type a question such as "What is the average salary?". The agent sends only the dataframe **schema + a small sample** to Google Gemini, asks it to write pandas code, then **executes that code locally** over your full dataset in a constrained environment. It returns a plain-language answer, the executed pandas code (so you can verify it references your real columns), and the intermediate steps / captured output. If the generated code errors, the agent feeds the error back to the model and retries (bounded) instead of surfacing a raw stack trace.

---

## Prerequisites

- **[`uv`](https://docs.astral.sh/uv/)** — Python environment & runner. Every Python command below is prefixed with `uv run`.
- **[`pnpm`](https://pnpm.io/)** — to build the frontend (a Next.js static export served by the backend).
- **A Google Gemini API key.** Copy the template and set the key:

  ```bash
  cp .env.example .env
  ```

  Then edit `.env` and set:

  ```
  AGENT_GEMINI_API_KEY=<your key>
  ```

  The default model is **`gemini-2.5-pro`**. To use a different model, set `AGENT_LLM_MODEL` in `.env` (e.g. `AGENT_LLM_MODEL=gemini-2.5-flash`).

---

## Run It

Run these in order, all from the repo root:

```bash
# 1. Build the frontend (the only command that cd's, and it returns to the root)
cd frontend && pnpm install && pnpm build && cd ..

# 2. Create the local database tables
uv run alembic upgrade head

# 3. Verify the migration applied — this must print a revision (0002), not blank
uv run alembic current

# 4. Start the server
uv run python -m src
```

Then open **http://localhost:8001/app/** in your browser (note the port `8001`, the `/app/`, and the **trailing slash**).

`uv run alembic current` should print something containing `0002 (head)`. Blank output means no migration was applied — re-run step 2.

---

## How to Test It

1. On the page at `http://localhost:8001/app/`, click the upload area and choose a CSV (a small employees or sales file works well).
2. Type a question, e.g. **"What is the average salary?"** or **"How many rows are there per department?"**, and submit.
3. Expect:
   - a **plain-language answer**,
   - below it, a panel showing the **pandas code that was run** (it references your real column names), and
   - the **intermediate steps / captured output** of running that code.

### Labelled "Coming soon" stubs (not bugs)

The UI shows a few intentionally non-functional, greyed-out placeholders tagged **"Coming soon"** — these are roadmap markers, not broken features:

- **Excel (`.xlsx`)** upload option — Phase 2.
- **Visualize / charts** toggle — deferred (post-v1).
- **History** panel — deferred (post-v1).

### Later phases

- **Phase 2** — Excel (`.xlsx`) upload: the same flow for spreadsheet files.
- **Phase 3** — Large files (100k+ rows): bounded sampling, memory guards, and execution timeouts tuned for scale, with a progress indicator.

---

## Data Locality

Your raw data never leaves the machine. The full file and parsed dataframe live only on the local filesystem (`data/uploads/`) and the local SQLite database. Only the dataframe **schema plus a small bounded sample/profile** is sent to the Gemini API — never your full rows. The executed code is always shown so every answer is auditable.

---

## Running the Tests (Gate)

```bash
uv run pytest tests/phase1 -q
```

These tests run against the **real Gemini API** using the key in `.env` (`AGENT_GEMINI_API_KEY`). The integration test uploads a small fixture CSV, asks a question with a known numeric answer, and asserts the response contains a correct computed `result_value`, a non-empty `code` field referencing a real column name, and non-empty `steps`. If `AGENT_GEMINI_API_KEY` is unset the real-Gemini test is skipped — and a skip **blocks** the gate.

To run the whole suite (unit + integration + phase gates):

```bash
uv run pytest -q
```

---

## Project Layout

```
src/
  api/            ← FastAPI routers (health, datasets, analyses) + static /app mount
  config/         ← Pydantic settings (env prefix AGENT_)
  datasets/       ← CSV parse, local storage, schema/profile extraction
  db/             ← SQLAlchemy models (datasets, analyses) + session
  domain/         ← Pydantic request/response models
  execution/      ← local pandas code sandbox
  graph/          ← LangGraph nodes/edges/state/runner (the analysis loop)
  llm/            ← LLM client + Gemini provider
  prompts/        ← analyze.md system prompt
  observability/  ← structured logging
frontend/         ← Next.js static export (served by FastAPI at /app)
tests/            ← unit/ (no key) + integration/ + phase1/ (real Gemini via .env)
alembic/          ← migrations (0001 baseline, 0002 datasets + analyses)
```
