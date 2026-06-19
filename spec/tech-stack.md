# Tech Stack

> EMPTY TEMPLATE — the spec-writer fills the `<!-- FILL IN -->` markers from the user's choices.
> The locked stack lives in [`harness/harness.md`](../harness/harness.md); this file records only the
> per-build decisions. Defaults below are the harness defaults — keep them unless the user overrides.
> **Verify the latest library + model versions before pinning** — a guessed/old version 404s. Pin
> CURRENT versions at build time (`pip index versions <pkg>`, the provider's models list).

## Runtime LLM (the PRODUCT's model — separate from Claude Code, which builds this)

Claude Code builds this product. The PRODUCT's runtime LLM is
set here and **defaults to a CHEAP tier** (Haiku / Gemini-flash class) — see `agent/config.py` defaults
(`harness/recipes/llm-providers.md`). Override only when the task needs more capability.

- Provider: <!-- FILL IN: anthropic | openai | google --> (default `anthropic`)
- Runtime model: <!-- FILL IN --> (default `claude-haiku-4-5-20251001` — cheap tier)
- API key env var: `APP_LLM_API_KEY` (pydantic-settings, prefix `APP_`)

### Models table — VERIFY before pinning (do not paste a date suffix you guessed)

| Provider  | Cheap (default tier)         | Mid                  | Frontier            |
|-----------|------------------------------|----------------------|---------------------|
| Anthropic | `claude-haiku-4-5-20251001`  | `claude-sonnet-4-6`  | `claude-opus-4-8`   |
| OpenAI    | `gpt-5.4-nano`               | `gpt-5.4-mini`       | `gpt-5.4`           |
| Google    | `gemini-3.5-flash` / `gemini-2.5-flash` | `gemini-3.5-flash` | `gemini-3.5-pro` |

Anthropic pricing & limits (verify at platform.claude.com before pinning):

| Model ID                      | $/MTok in | $/MTok out | Context | Max output |
|-------------------------------|-----------|------------|---------|------------|
| `claude-haiku-4-5-20251001`   | $1        | $5         | 200K    | 64K        |
| `claude-sonnet-4-6`           | $3        | $15        | 1M      | 64K        |
| `claude-opus-4-8`             | $5        | $25        | 1M      | 128K       |

The runtime model is wired via `init_chat_model` so the provider/model strings above are the only change
needed to switch tiers — `harness/recipes/llm-providers.md`.

## Persistence

Local-first by default; the SAME async code runs on both — only the URL changes (`harness/recipes/durability.md`).

- Local (DEMO): SQLite via **aiosqlite** — `sqlite+aiosqlite:///./agent.db` (the `APP_DATABASE_URL` default)
- Prod (PRODUCTIONISE): PostgreSQL via **asyncpg** — `postgresql+asyncpg://...`
- ORM: async SQLAlchemy 2.0. **NEVER psycopg2** (sync — breaks the async stack).
- Tables: `runs`, `messages`, `spans` (+ domain entities below).
- Domain entities: <!-- FILL IN: tables beyond runs/messages/spans, or "none" -->

## Deploy target

- Target: <!-- FILL IN: TBD | Railway | Fly.io | Modal --> (default `TBD` — chosen at PRODUCTIONISE)
- Artifact: portable build (`langgraph build` / `langgraph.json`, Dockerfile) — `harness/recipes/durability.md`
- Prod ladder: PostgreSQL + Redis (Layer 11 "Deploy & Operate").

## Key libraries (pin CURRENT versions at build time — verify, don't guess)

| Concern             | Library                                  | Notes |
|---------------------|------------------------------------------|-------|
| Web / SSE           | `fastapi`, `uvicorn`                      | async, SSE streaming |
| Orchestration       | `langgraph`, `langchain`, `langchain-core` | StateGraph + ReAct; `init_chat_model` |
| LLM provider SDK    | one of `langchain-anthropic` / `-openai` / `-google-genai` | match the provider above |
| DB (local)          | `sqlalchemy[asyncio]`, `aiosqlite`       | local-first default |
| DB (prod)           | `asyncpg`                                | added at PRODUCTIONISE; NEVER psycopg2 |
| Settings            | `pydantic-settings`                      | env prefix `APP_` |
| Observability       | `opentelemetry-api` / `-sdk`             | OTel-GenAI spans → SQLite; opt-in OTLP export |
| MCP (external only) | `langchain-mcp-adapters` / `mcp`         | EXTERNAL integrations only — see What to avoid |
| Tests               | `pytest`, `pytest-asyncio`               | FakeModel drives the loop with no API key |

## What to avoid (load-bearing — do not relitigate; full rationale in `harness/harness.md`)

- **No `psycopg2` / any sync DB driver** — the whole stack is async (aiosqlite / asyncpg only).
- **No MCP for internal tools** — internal tools are plain typed `@tool` in-process. MCP is for EXTERNAL
  integrations only, and with **OAuth 2.1 (no static secrets)** — `harness/recipes/tools-and-mcp.md`.
- **No guessed/old library or model versions** — a stale pin 404s. Verify latest, then pin.
- **No frontier model as the runtime default** — default cheap; upgrade tier only when justified.
- **No Pydantic AI here** — LangGraph is the build target; Pydantic AI is the documented alternative only.
- **No secrets in code** — config via `APP_`-prefixed env / `.env` (pydantic-settings).
