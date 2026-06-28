# DataChat

> **All commands run from the repo root.** There is no subdirectory to `cd` into — the repo root *is* the project. Every Python/Alembic/Uvicorn command below is prefixed with `uv run`; bare `alembic`/`pytest`/`python` will fail unless you have manually activated the venv.

DataChat is a personal, locally-run CSV data-analysis agent for a single owner. Upload a CSV, then ask plain-English questions about it. For each question a LangGraph plan-execute agent **plans** the analysis, **generates pandas code**, **runs that code locally against your full file**, and **synthesizes** a plain-English answer with the key numbers and a summary table — streamed back to the browser. Every run (question, plan, code, result, tokens, cost) is persisted to SQLite as an immutable, browsable audit trail.

**The privacy boundary is the load-bearing rule:** only the column schema + a small sample of rows + the profile reach the Gemini API. Your full dataset never leaves the machine — the generated pandas code runs locally in-process against the full file.

---

## Requirements

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node 18+ and `pnpm` (to build the static frontend)
- A Google Gemini API key

---

## Setup

```bash
cp .env.example .env
# Edit .env and set AGENT_GEMINI_API_KEY=<your key>
uv sync --extra dev
```

`.env` only needs **`AGENT_GEMINI_API_KEY`** for the agent to run. Everything else has a working default (see `.env.example`).

### Environment variables

All variables use the `AGENT_` prefix and are documented in [`.env.example`](.env.example). The ones you care about:

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_GEMINI_API_KEY` | — (**required**) | Your Gemini API key (presence-only; never logged) |
| `AGENT_LLM_MODEL` | `gemini-2.5-flash` | Gemini model. See the model note below. |
| `AGENT_DATABASE_URL` | `sqlite:///./data/agent.db` | SQLite file (the production DB for this single local owner) |
| `AGENT_SAMPLE_ROWS` | `20` | Max sample rows sent to the LLM (the privacy bound) |
| `AGENT_HISTORY_TURNS` | `6` | Conversation turns fed back into the prompt |
| `AGENT_EXEC_TIMEOUT_S` | `30` | Wall-clock timeout for locally-executed generated code |
| `AGENT_MAX_RETRIES` | `1` | Self-correction retries on a code-execution failure |
| `AGENT_MAX_UPLOAD_MB` | `100` | Max upload size; larger files are rejected (413) |
| `AGENT_PRICE_INPUT_PER_M` / `AGENT_PRICE_OUTPUT_PER_M` | `0.10` / `0.40` | USD per 1M tokens, used to compute per-question cost |

> **Model note:** the working default is **`gemini-2.5-flash`**. The original spec intended `gemini-2.0-flash`, but that model currently returns `404 'no longer available'` for new API keys, so DataChat defaults to `gemini-2.5-flash`. Override with `AGENT_LLM_MODEL` once `gemini-2.0-flash` is restored for your key.

---

## Run (Phase 1)

All commands run from the **repo root**, in order:

```bash
# 1. Apply the database migrations (creates the datasets + messages tables)
uv run alembic upgrade head

# 2. Verify a revision is applied — this MUST print "0002 (head)", not blank.
uv run alembic current

# 3. Build the static frontend once (note the cd into frontend/ and back out)
cd frontend && pnpm install && pnpm build && cd ..

# 4. Start the single-origin server on :8001
uv run python -m src
```

Then open **<http://localhost:8001/app/>** in your browser.

If step 2 prints nothing, the migration did not apply — re-run `uv run alembic upgrade head`.

---

## Endpoints

The frontend at `/app/` calls these same-origin `/api/...` routes. Every JSON route returns the envelope `{"data": ..., "error": null}`, or on error `{"detail": {"code", "message"}}`.

| Method | Path | Phase 1 | Purpose |
|--------|------|---------|---------|
| `POST` | `/api/datasets` | **REAL** | Upload a CSV (`multipart/form-data` `file`); profile it locally (pandas, no LLM); returns `{dataset_id, name, profile}`. |
| `POST` | `/api/datasets/{id}/ask` | **REAL** (streaming) | Ask a question (JSON `{question}`); streams the answer back via Server-Sent Events. |
| `GET`  | `/api/datasets/{id}` | **REAL** | Load a dataset + its full conversation thread (rehydrates across days). |
| `GET`  | `/api/datasets/{id}/messages` | **REAL** | Run-history summaries for a dataset, oldest first. |
| `GET`  | `/api/messages/{id}` | **REAL** | The full record of one run (plan, code, answer, numbers, tokens, cost, error). |
| `GET`  | `/api/datasets` | **STUB** | Library list. Phase 1 returns the active datasets; the persistent multi-dataset library / cross-day reopening from the sidebar / derived-dataset saving become real in **Phase 3**. |
| `GET`  | `/health` | — | Liveness: `{"data": {"status": "ok"}, "error": null}`. |

### The `ask` SSE event sequence

`POST /api/datasets/{id}/ask` returns `text/event-stream`. Events, in order:

- `event: status` → `{"step": "planning" | "generating_code" | "executing" | "synthesizing"}`
- `event: plan` → `{"plan": "1. ...\n2. ..."}`
- `event: code` → `{"code": "result = ..."}`
- `event: token` → `{"text": "<next chunk of the answer>"}` (repeated, streamed live)
- `event: done` → `{"message_id", "key_numbers", "result_table", "prompt_tokens", "completion_tokens", "cost_usd", "status": "completed"}`
- `event: error` → `{"message_id", "error", "code", "status": "failed"}` — an analysis failure **rides the stream**; the server does not 500 mid-stream.

Pre-stream errors are returned as normal HTTP responses: `400 EMPTY_QUESTION` (blank question), `404 NOT_FOUND` (unknown dataset). Upload errors: `400 UNSUPPORTED_TYPE` (non-CSV), `400 MALFORMED_FILE` (unparseable CSV), `413 FILE_TOO_LARGE`, `500 UPLOAD_FAILED`.

### Quick check with curl

```bash
# Upload and capture the dataset id
curl -F file=@tests/fixtures/small_sales.csv http://localhost:8001/api/datasets

# Stream an answer (-N disables curl's buffering so tokens arrive live)
curl -N -X POST http://localhost:8001/api/datasets/<dataset_id>/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many rows are there?"}'
```

---

## What's REAL vs STUB in Phase 1

- **REAL** — single-dataset upload + local profiling; the full plan → generate-code → execute-local → synthesize loop streamed over SSE; per-question tokens/cost; the persisted audit trail; reopening the active dataset's thread.
- **STUB** — the persistent multi-dataset **library** sidebar (`GET /api/datasets` is a placeholder), saving derived/cleaned datasets, deleting datasets, charts, and the daily cost total. These become real in later phases and are labelled as stubs in the UI.

## The privacy boundary

| Goes to Gemini | Stays 100% local |
|----------------|------------------|
| Column names + inferred dtypes | The full dataset (all rows/cells) |
| Up to `AGENT_SAMPLE_ROWS` (default 20) sample rows | The uploaded file on disk (`data/uploads/`) |
| Per-column ranges / missing counts (the profile) | All computed results |
| Your question + trimmed history | — |

Profiling makes **no** LLM call (pure pandas). The generated pandas code is what touches the full data, and it runs **locally** in this process.

---

## Tests

```bash
uv run pytest -q          # whole suite (integration tests hit real Gemini via .env)
uv run pytest tests/unit/ -q   # unit only
```

Integration and the streamed-SSE tests run against the **real Gemini API** using the key in `.env`; they `pytest.skip` only if the key is genuinely absent. SQLite is the production database here (a single local owner), so tests run against SQLite too — not a substitute.

---

## Layout

```
src/
  api/            ← FastAPI routes: datasets (upload, ask/SSE, get, history), health
  config/         ← Pydantic settings (AGENT_ prefix)
  db/             ← SQLAlchemy models (datasets, messages) + session
  domain/         ← Pydantic Dataset / Message views
  execution/      ← profile.py (local pandas profiling), sandbox.py (local code execution)
  graph/          ← LangGraph plan-execute agent + streaming runner
  llm/            ← Gemini client wrapper (the only path to the model)
  observability/  ← structlog JSON logs
frontend/         ← Next.js static export, served by FastAPI at /app/
tests/            ← unit / integration / e2e
alembic/          ← migrations (0002 adds datasets + messages)
```
