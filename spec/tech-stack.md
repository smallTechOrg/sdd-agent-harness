# Tech Stack — DataChat

> Part 4 of the 4-part spec contract (see `harness/harness.md`). Records the per-build decisions that drive
> `agent/config.py`. **Verify the latest library + model versions before pinning at build time** — a
> guessed/old version 404s. The locked stack (async, FastAPI, LangGraph, async SQLAlchemy, SQLite→Postgres)
> is not relitigated here; only the choices below are.

## Runtime LLM (the PRODUCT's model — separate from the coding agent that builds this)

| Setting | Value | Env var |
|---------|-------|---------|
| Provider | `google_genai` | `APP_LLM_PROVIDER` |
| Runtime model (CHEAP tier) | `gemini-2.5-flash` | `APP_LLM_MODEL` |
| API key | funded, in `.env` (gitignored) — **present & verified** (used in this repo's real-Gemini self-test) | `APP_LLM_API_KEY` |
| Escalation model | none in scope — revisit only if SQL-generation quality on complex questions proves insufficient | per-call override |

`gemini-2.5-flash` is the cheap/fast tier for `google_genai` and is **already configured and funded** in
`.env`; it is capable for schema-grounded SQL generation, chart-spec authoring, and multi-turn analysis.
The runtime model is wired via `init_chat_model`, so switching provider/tier is a config change, not a code
change (`harness/patterns/model-and-providers.md`). The LLM-as-judge for evals defaults to the same model.

## Persistence

Local-first by default; the SAME async code runs on both rungs — only the URL (and saver class) changes.

- Local (DEMO): SQLite via **aiosqlite** — `sqlite+aiosqlite:///./agent.db` (the `APP_DATABASE_URL` default)
- Prod (PRODUCTIONISE): PostgreSQL via **asyncpg** — `postgresql+asyncpg://...` (via `/deploy`)
- ORM: async SQLAlchemy 2.0. **NEVER psycopg2** (sync — breaks the async stack).
- Core tables: `runs`, `messages`, `spans`.
- Domain entities (SQLite metadata): `datasets`, `data_tables`, `conversations`, `conversation_turns`, `charts` — see `spec/agent.md` § Domain tables.
- **Analytical data store: DuckDB** — the user's uploaded tabular data lives in a per-dataset DuckDB file
  (e.g. `./data/<dataset_id>.duckdb`), **not** in SQLite. Ingest uses a write-connection (server-only); the
  agent's `run_sql` uses a separate `read_only=True` connection. DuckDB reads CSV/JSON natively.
- Multi-turn checkpointer (L8): `AsyncSqliteSaver` local → `AsyncPostgresSaver` prod (`langgraph-checkpoint-*`).

## Tools (3-layer model — `harness/patterns/tools-and-mcp.md`)
- In-process (typed `@tool`): `get_schema`, `run_sql` (read-only DuckDB), `create_chart` (Vega-Lite v5), `write_todos`, `finish`.
- MCP (external integrations only): **none** — nothing crosses a process/trust boundary.
- Skills / CLI: none.

## Interface — `harness/patterns/interface.md`
- Web UI: **yes** — Next.js (App Router) + React + Tailwind. Primary journey: create/select a dataset →
  upload files → ask a question → see the grounded answer + any chart (Vega-Lite via `vega-embed`) → deep-link
  to its `/traces`. Multi-turn chat thread. Does not re-implement the `/traces` viewer.
- API endpoints (FastAPI): `GET /health`, `POST /runs` (`{goal, conversation_id?}` → answer + chart refs),
  `POST /datasets`, `POST /datasets/{id}/files`, `GET /datasets/{id}` (schema), `POST /conversations`,
  `GET /traces`.
- Streaming: SSE token streaming is optional (nice-to-have for the chat UX); Phase 1 `POST /runs` returns
  the full answer. Add `/runs/stream` later if wanted (`harness/patterns/interface.md` § SSE).

## Deploy target — `harness/patterns/deploy.md`
- Target host: **TBD** (chosen at `/deploy`; Railway recommended for least-ops, else Fly.io / Modal).
- Artifact: portable build — both `langgraph.json` (`langgraph build`) and a `Dockerfile` ship.
- Prod ladder: PostgreSQL (`asyncpg`) + `AsyncPostgresSaver` checkpointer; Redis only if multi-replica.

## Key libraries (pin CURRENT versions at build time — verify, don't guess)

| Concern | Library | Notes |
|---------|---------|-------|
| Web / SSE | `fastapi`, `uvicorn`, `python-multipart` | async; multipart for file upload |
| Orchestration | `langgraph`, `langchain`, `langchain-core` | StateGraph + ReAct; `init_chat_model` |
| LLM provider SDK | `langchain-google-genai` | matches `APP_LLM_PROVIDER=google_genai` |
| Analytical engine | `duckdb` | per-dataset store; native CSV/JSON read; `read_only=True` for the agent |
| DB (local) | `sqlalchemy[asyncio]`, `aiosqlite` | local-first metadata + spine |
| DB (prod) | `asyncpg` | added at `/deploy`; **NEVER psycopg2** |
| Checkpointer | `langgraph-checkpoint-sqlite` (local), `langgraph-checkpoint-postgres` (prod) | multi-turn threads (L8) |
| Settings | `pydantic-settings` | env prefix `APP_` |
| Observability | `opentelemetry-api` / `-sdk` | OTel-GenAI spans → SQLite; opt-in OTLP export |
| Tests | `pytest`, `pytest-asyncio`, `httpx` | FakeModel drives the loop with no key; httpx for API tests |
| UI e2e gate | `playwright` | asserts the post-JS DOM (answer + chart + trace link) |
| UI (Node) | `next`, `react`, `tailwindcss`, `vega`, `vega-lite`, `vega-embed` | chat UI + client-side chart render |

Example `.env` (the only thing that differs local↔prod is environment):
```
APP_LLM_PROVIDER=google_genai
APP_LLM_MODEL=gemini-2.5-flash      # CHEAP tier — verified working in this repo
APP_LLM_API_KEY=                    # funded key, .env only — never committed
APP_DATABASE_URL=sqlite+aiosqlite:///./agent.db   # local-first; Postgres+asyncpg at /deploy
APP_PORT=8001
APP_MAX_ITERATIONS=6
APP_DURABILITY_ENABLED=false        # true for multi-turn conversations; false for the single-turn demo gate
```

## What to avoid (load-bearing — full rationale in `harness/harness.md`)
- **No `psycopg2` / any sync DB driver** — the whole stack is async (aiosqlite / asyncpg / duckdb sync calls run off the loop or are fast/local).
- **No write access for the agent** — `run_sql` is read-only by construction (DuckDB `read_only=True` + statement allowlist); ingest's write-connection is never exposed to the model.
- **No MCP** — every tool is owned and in-process; MCP is for external integrations only.
- **No guessed/old library or model versions** — verify latest, then pin.
- **No frontier model as the runtime default** — `gemini-2.5-flash` (cheap tier); escalate only on a stated need.
- **No secrets in code** — config via `APP_`-prefixed env / `.env` (pydantic-settings); the model sees tool names, never the key.
