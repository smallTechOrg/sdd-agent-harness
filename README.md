# Data Analysis Agent

Upload CSV files and ask natural-language questions about your data. The agent writes and executes Python/pandas code, retries on error (up to 5 times), and returns a streaming plain-text answer with an interactive Plotly chart and per-query cost tracking.

> All commands run from the repo root.

---

## Setup

### 1. Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Node.js >= 20](https://nodejs.org/) + [pnpm](https://pnpm.io/)
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### 2. Install Python dependencies

```bash
uv sync
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set AGENT_GEMINI_API_KEY=<your-key>
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
uv run alembic current   # must show a revision hash — not blank
```

### 5. Build the frontend

```bash
cd frontend && pnpm install && pnpm build && cd ..
```

---

## Running

```bash
uv run python -m src
```

Then open **http://localhost:8001/app/** in your browser.

---

## Using the Agent

1. **Upload a CSV** — click "+ Upload CSV" in the left sidebar. The agent profiles it immediately (column names, types, row count, nulls, 3 sample rows).
2. **Ask a question** — type a natural-language question in the chat box, e.g. "What is the average sales by region?"
3. **See the answer** — the agent streams back a plain-text answer with an interactive Plotly chart and collapsible Python code steps.
4. **Check the cost** — token count and estimated cost (USD) appear below each answer.

---

## Running Tests

```bash
# All unit + integration tests (uses real Gemini API key from .env):
uv run pytest tests/phase1/ -x -q

# With the live app running (separate terminal: uv run python -m src):
uv run pytest tests/phase1/ tests/e2e/ -x -q
```

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/api/files/upload` | POST | Upload a CSV file (multipart/form-data) |
| `/api/files` | GET | List uploaded files |
| `/api/query/stream` | POST | Stream analysis answer (Server-Sent Events) |
| `/api/sessions` | GET | Session list (Phase 2 stub — returns empty list) |

Interactive docs: **http://localhost:8001/docs**

---

## Phase 1 — What is real, what is a stub

**Real (Phase 1):**
- CSV file upload with instant auto-profiling (column names, types, null counts, sample values)
- Natural-language query → multi-step Python/pandas code generation and execution (up to 5 retries on error)
- Streaming answer via Server-Sent Events + interactive Plotly chart + collapsible code accordion
- Per-query input/output token count and estimated cost (USD)

**Clearly-labelled stubs (coming in Phase 2):**
- "Multi-file join — Coming in Phase 2" (sidebar)
- "Session history — Coming in Phase 2" (chat panel header)
- Excel (.xlsx) file upload

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AGENT_GEMINI_API_KEY` | _(required)_ | Google Gemini API key |
| `AGENT_DATABASE_URL` | `sqlite:///./data_analysis.db` | SQLite database path |
| `AGENT_LLM_MODEL` | `gemini-2.5-flash` | Gemini model ID |
| `AGENT_LOG_LEVEL` | `INFO` | Log level |
| `AGENT_COST_INPUT_PER_1K` | `0.000125` | Cost per 1 000 input tokens (USD) |
| `AGENT_COST_OUTPUT_PER_1K` | `0.000375` | Cost per 1 000 output tokens (USD) |

---

## Repo Layout

```
src/                     <- application package (importable as data_analysis.*)
  data_analysis/
    api/                 <- FastAPI routers (upload, query, sessions, health)
    config/              <- Pydantic BaseSettings
    db/                  <- SQLAlchemy models + session
    domain/              <- Pydantic request/response models
    graph/               <- LangGraph agent (code-gen, execute, retry, summarise)
    llm/                 <- Gemini client
    observability/       <- structured logging
    prompts/             <- prompt templates (.md)
    tools/               <- code executor (pandas sandbox)
frontend/                <- Next.js static export (served by FastAPI at /app)
tests/
  phase1/                <- integration tests (upload + query, real Gemini key)
  e2e/                   <- Playwright browser tests (live app on port 8001)
spec/                    <- spec: roadmap, architecture, capabilities, data, api, ui, agent
harness/
  rules/                 <- ai-agents, git, secret-hygiene
  patterns/              <- spec-driven, phases, project-layout, tech-stack, code, ...
.claude/
  skills/                <- /zero-shot-build, /zero-shot-fix, /zero-shot-sync
  agents/                <- agent-builder, spec-writer, code-generator, qa-auditor
CLAUDE.md
pyproject.toml
alembic.ini
.env.example
```
