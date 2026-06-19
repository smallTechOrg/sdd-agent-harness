# Tech Stack

Per-build decisions for the data analysis agent. Defaults follow harness rules
(`harness/harness.md`); every field below is filled — no `<!-- FILL IN -->` markers remain.
Verify new versions at the next build: a stale pin 404s.

## Runtime LLM

Claude Code builds this product. The product's runtime LLM is set here.

- **Provider:** `google_genai`
  Rationale: user-specified; cheap-tier is the default within this provider.
- **Runtime model:** `gemini-2.5-flash`
  Rationale: user-specified cheap tier. Verified against Google AI docs and the
  `langchain-google-genai` integration page — the stable ID has no date suffix.
  NL-to-SQL + chart-spec generation on short-to-medium context is well within the
  flash tier's capability; no escalation needed.
- **API key env var:** `APP_LLM_API_KEY` (pydantic-settings, prefix `APP_`)
- **Provider package:** `langchain-google-genai==4.2.5` (verified on PyPI 2026-06-19)

Wire-up: `init_chat_model(model, model_provider="google_genai", api_key=...)` —
switching provider stays a config change, never a code change. See
`harness/patterns/model-and-providers.md`.

## Persistence

Local-first; the same async code runs on both rungs — only the URL changes.
See `harness/patterns/persistence.md`.

- **Local (demo gate):** `sqlite+aiosqlite:///./agent.db`
- **Prod (productionise):** `postgresql+asyncpg://user:pw@host/db` — swap URL only at
  `/deploy`; **never `psycopg2`** (sync, blocks the event loop).
- **ORM:** async SQLAlchemy 2.0 (`sqlalchemy[asyncio]==2.0.51`)
- **Local driver:** `aiosqlite==0.22.1`
- **Prod driver:** `asyncpg==0.31.0` (added at productionise; not needed for demo gate)

### Domain entities (extend the same `Base` — `agent/domain.py`)

These join `runs`, `messages`, `spans` on the same `Base` and are created by `init_db()`.
Foreign keys reference `runs.id` so domain rows tie back to the run that produced them.

| Table | Columns | Notes |
|---|---|---|
| `datasets` | `id` (PK, uuid), `name` (String), `created_at` (DateTime+tz), `row_count` (Integer), `column_info` (JSON) | One row per uploaded CSV/JSON after ingestion |
| `uploaded_files` | `id` (PK, uuid), `dataset_id` (FK → datasets.id, indexed), `original_filename` (String), `stored_path` (String), `created_at` (DateTime+tz) | Raw file record; `stored_path` is the local filesystem path |

## Interface

- **Web UI:** Next.js + React + Tailwind — upload page, chat panel, chart rendering, `/traces` viewer
- **Backend API:** FastAPI (`fastapi==0.137.2`) with SSE token streaming
- **SSE server:** `uvicorn==0.49.0` (ASGI, async end-to-end)
- **Port:** `APP_PORT=8001`

## Deploy

- **Artifacts:** both ship every build — `langgraph.json` (managed runtime path) and
  `Dockerfile` (portable uvicorn path). See `harness/patterns/deploy.md`.
- **Host:** TBD — chosen at `/deploy`. Railway is recommended for non-experts (managed
  Postgres + Redis plugin, minimal ops); Fly.io for multi-region; Modal for bursty/serverless.
- **Prod ladder:** Postgres (`asyncpg`) + Redis (for multi-replica streaming/queue). Redis
  is productionise-only — a single-replica demo needs neither.
- **Migrations:** `create_all` for local dev; Alembic at productionise when Postgres has
  data that can't be dropped.

## Tools — in-process `@tool` only (no MCP needed)

All tools are owned, local, and cross no process/trust boundary — plain typed `@tool`
in `agent/tools.py`. See `harness/patterns/tools-and-mcp.md`.

| Tool | Action class | Purpose |
|---|---|---|
| `list_datasets` | read-only | Return names + IDs of ingested datasets |
| `execute_sql` | read-only | Run a parameterised SELECT against the agent DB and return rows as JSON string |
| `get_dataset_schema` | read-only | Return column names, types, and a row-count for a dataset |
| `generate_chart_spec` | read-only | Build a Plotly JSON spec from a dataset + column selections for the UI to render |
| `finish` | terminal | Return the final answer and end the run (called exactly once) |

No MCP servers — the product is local-only with no external SaaS integrations.

## Key libraries — pinned, verified on PyPI 2026-06-19

| Concern | Package | Pinned version |
|---|---|---|
| Web / SSE | `fastapi` | `0.137.2` |
| ASGI server | `uvicorn` | `0.49.0` |
| Orchestration | `langgraph` | `1.2.6` |
| LangChain core | `langchain` | `1.3.10` |
| LangChain core | `langchain-core` | `1.4.8` |
| LLM provider SDK | `langchain-google-genai` | `4.2.5` |
| ORM | `sqlalchemy[asyncio]` | `2.0.51` |
| Local DB driver | `aiosqlite` | `0.22.1` |
| Prod DB driver | `asyncpg` | `0.31.0` |
| Settings | `pydantic-settings` | `2.14.2` |
| Observability | `opentelemetry-api` | `1.42.1` |
| Observability | `opentelemetry-sdk` | `1.42.1` |
| Data processing | `pandas` | `3.0.3` |
| Chart spec gen | `plotly` | `6.8.0` |
| Tests | `pytest` | `9.1.1` |
| Tests (async) | `pytest-asyncio` | `1.1.0` |

`asyncpg` is prod-only — include it in `requirements.txt` but it is not exercised at the
demo gate (which runs SQLite). `pandas` requires Python ≥ 3.11; pin `python_version = "3.12"`
in `langgraph.json` and the `Dockerfile`.

## Agent settings — `agent/config.py` defaults

```
APP_LLM_PROVIDER=google_genai
APP_LLM_MODEL=gemini-2.5-flash
APP_LLM_API_KEY=                          # funded key — injected env / .env, never committed
APP_DATABASE_URL=sqlite+aiosqlite:///./agent.db   # local-first; swap to postgresql+asyncpg at /deploy
APP_PORT=8001
APP_MAX_ITERATIONS=6
```

## What this file drives

`spec/tech-stack.md` → `agent/config.py` (`Settings`, env prefix `APP_`) → every recipe
that calls `get_settings()`. The only difference between local and prod is the environment
variables above — no code changes required.
