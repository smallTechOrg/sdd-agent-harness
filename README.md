# Data Analysis Agent

All commands run from the repo root unless specified otherwise.

A fully-local data analysis tool. Upload CSV or Excel files via a browser chat UI; ask natural-language questions; receive SQL, a prose narrative with key statistics, and inline charts — all powered by Gemini and running entirely on your machine. No data leaves your machine except the schema context and statistics JSON sent to the Gemini API.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_GEMINI_API_KEY` | Yes | Google Gemini API key for SQL generation and prose narrative |
| `AGENT_DATABASE_URL` | No | SQLite path (default: `sqlite:///./data/agent.db`) |
| `AGENT_LLM_MODEL` | No | Model name override (default: `gemini-2.5-pro`) |

Create a `.env` file at the repo root:

```
AGENT_GEMINI_API_KEY=your-key-here
AGENT_DATABASE_URL=sqlite:///./data/agent.db
AGENT_LLM_MODEL=gemini-2.5-pro
```

---

## Setup

```bash
# Install Python dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Verify migration is at head
uv run alembic current
```

---

## Build Frontend

```bash
cd frontend && pnpm install && pnpm build
```

---

## Run

```bash
uv run python -m src
```

Open `http://localhost:8001/app/` in your browser.

---

## Test

```bash
uv run pytest tests/test_phase1_backend.py -v
```

Integration tests hit the real Gemini API using your `AGENT_GEMINI_API_KEY`. Tests that require the API key skip automatically when the key is absent.

---

## Usage

1. Ensure `.env` contains `AGENT_GEMINI_API_KEY=<your-key>`.
2. Run migrations: `uv run alembic upgrade head`
3. Build frontend: `cd frontend && pnpm install && pnpm build`
4. Start server: `uv run python -m src`
5. Open `http://localhost:8001/app/`
6. Drag a CSV file onto the drop zone in the left sidebar. A green pill badge appears with the table name and row count.
7. Type a question in the message input (e.g. "What is the average value per category?") and click Analyze.
8. The agent returns: a collapsible "SQL used" section, a prose narrative with key statistics, and at least one inline chart.

---

## Constraints

- Files must be `.csv`, `.xlsx`, or `.xls` — maximum 50 MB and 500,000 rows.
- All uploaded data stays on your disk; only schema context and statistics JSON are sent to Gemini.
- SQLite only in Phase 1-3; PostgreSQL connectivity is Phase 4.
- Charts are rendered client-side via Recharts; no server-side image generation.
