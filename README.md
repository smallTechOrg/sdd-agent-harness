# Data Analysis Agent

Upload a CSV or Excel file, ask a natural-language question, get a chart and a plain-English summary — powered by Gemini + LangGraph + FastAPI.

---

## What It Does

1. **Upload a dataset** — CSV or Excel (up to any size; only the schema and 20 sample rows are sent to Gemini for privacy)
2. **Ask a question** — "Show me total revenue by month" or "Which product sold most?"
3. **Get a chart** — Gemini decides the chart type (bar, line, scatter); pandas runs the aggregation locally against the full dataset; you get labels, values, and a 2–3 sentence summary

---

## Setup

```bash
# 1. Clone and enter the directory
git clone <repo-url> my-agent
cd my-agent

# 2. Install dependencies
uv sync

# 3. Set your Gemini API key
cp .env.example .env
# Edit .env — set AGENT_GEMINI_API_KEY=<your key>

# 4. Run database migrations
uv run alembic upgrade head

# 5. (Optional) Build the frontend
cd frontend && pnpm install && pnpm build && cd ..

# 6. Start the server
uv run python -m src
```

The server listens on `http://localhost:8001`.

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | UI (requires frontend build) |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

---

## API

### POST /datasets

Upload a CSV or Excel file.

```bash
curl -X POST http://localhost:8001/datasets \
  -F "file=@path/to/data.csv"
```

Response:
```json
{
  "data": {
    "dataset_id": "abc123",
    "filename": "data.csv",
    "columns": ["month", "product", "revenue"],
    "row_count": 25
  },
  "error": null
}
```

### POST /analyze

Ask a question about an uploaded dataset.

```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "abc123", "question": "Show me total revenue by month"}'
```

Response:
```json
{
  "data": {
    "dataset_id": "abc123",
    "chart_type": "bar",
    "labels": ["January", "February", "March"],
    "values": [20500, 22700, 25800],
    "summary": "Revenue grew steadily across all months..."
  },
  "error": null
}
```

### GET /datasets

List all uploaded datasets.

```bash
curl http://localhost:8001/datasets
```

---

## Tests

```bash
# Unit tests — no API key required
uv run pytest tests/unit/ -v

# Integration tests — require AGENT_GEMINI_API_KEY in .env
uv run pytest tests/integration/ -v

# All tests
uv run pytest -v
```

---

## Environment Variables

Set in `.env` (never commit this file):

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_GEMINI_API_KEY` | Yes | Google Gemini API key |
| `AGENT_DATABASE_URL` | No | SQLAlchemy DB URL (default: `sqlite:///./data/agent.db`) |
| `AGENT_LLM_MODEL` | No | Override the Gemini model (default: `gemini-2.5-pro`) |

---

## Project Layout

```
src/
  api/          — FastAPI routers (health, datasets, analyze)
  config/       — Pydantic settings (reads from .env)
  db/           — SQLAlchemy models + session
  domain/       — Pydantic request/response models
  graph/        — LangGraph nodes, edges, state, runner
  llm/          — LLM client + providers (Gemini, Anthropic)
  prompts/      — Prompt templates (.md)
tests/
  unit/         — passes with no API key
  integration/  — requires real key in .env
  fixtures/     — test data (sales.csv)
data/uploads/   — uploaded files (gitignored except .gitkeep)
alembic/        — database migrations
frontend/       — Next.js static export (served at /app)
```

---

## How It Works

The backend is a **LangGraph agent** with three nodes:

1. `analyze_data` — loads the dataset from disk, sends schema + 20 sample rows to Gemini, receives pandas code + chart metadata, executes the code locally against the full DataFrame
2. `handle_error` — marks the run as failed
3. `finalize` — marks the run as completed

Privacy: **the full dataset never leaves your machine**. Only the column schema and up to 20 sample rows are sent to Gemini. All aggregation runs locally via pandas.

---

## Rules AI Agents Follow

Full rules in `harness/rules/ai-agents.md`. Summary:

- Read the full spec before writing any code
- Never skip a phase; commit every logical unit
- Tests run against the real LLM/API using keys from `.env` — stubbed runs do not count as passing
- Each phase is tested by the human before the next phase starts
