# Tech Stack

> EMPTY TEMPLATE — the spec-writer fills the `<!-- FILL IN -->` markers from the user's choices.
> The locked stack lives in [`harness/harness.md`](../harness/harness.md); this file records only the
> per-build decisions. Defaults below are the harness defaults — keep them unless the user overrides.
> This is the **reused tested-core** zone (code is truth, like a framework dependency — see
> `spec/constitution.md` § two-zone model); the per-build choices recorded here parameterize that core.
> **Verify the latest library + model versions before pinning** — a guessed/old version 404s, and a 404 at
> runtime almost always means a wrong/stale model name. Pin CURRENT versions at build time
> (`pip index versions <pkg>`, the provider's models list). Phase 1 is SQLite + `create_all` and dev port
> **8001**; alembic/Postgres move entirely into `/deploy`.

## Runtime LLM (the PRODUCT's model — separate from Claude Code, which builds this)

Claude Code builds this product. The PRODUCT's runtime LLM is **chosen at Q4 intake** (with the API key
collected in the same round — never mid-build) and **defaults to a CHEAP tier** (Haiku / Gemini-flash class)
so a non-technical owner can just hit enter. It is wired through LangChain's `init_chat_model` behind a thin
accessor (`agent/llm.py` — `harness/patterns/model-and-providers.md`); no bespoke SDK client lives in
the nodes. Switching tiers is two env vars, no code edit. **The runtime LLM is never stubbed** — even in v1,
the one real capability calls the real model (Decision #2).

- Provider: <!-- FILL IN: anthropic | openai | google --> (default `anthropic`) — env `APP_LLM_PROVIDER`
- Runtime model: <!-- FILL IN --> (default `claude-haiku-4-5` — cheap tier) — env `APP_LLM_MODEL`
- API key env var: `APP_LLM_API_KEY` (pydantic-settings, prefix `APP_`; collected at Q4 intake)

> A wrong/stale model name surfaces as a **404 at first real call** while the build looks green — verify the
> exact ID against the provider's models list before pinning, and pin a current one (the cheap-tier alias
> below resolves to the latest snapshot, so prefer the alias unless you need to pin a frozen snapshot).

### Models table — VERIFY before pinning (do not paste a date suffix you guessed)

| Provider  | Cheap (default tier)         | Mid                  | Frontier            |
|-----------|------------------------------|----------------------|---------------------|
| Anthropic | `claude-haiku-4-5`           | `claude-sonnet-4-6`  | `claude-opus-4-8`   |
| OpenAI    | `gpt-5-nano`                 | `gpt-5-mini`         | `gpt-5.4`           |
| Google    | `gemini-3.5-flash` / `gemini-2.5-flash` | `gemini-3.5-flash` | `gemini-3.5-pro` |

Anthropic pricing & limits (verified against the Claude model catalog — re-verify at platform.claude.com
before pinning; the cheap-tier alias resolves to full ID `claude-haiku-4-5-20251001`):

| Model ID            | $/MTok in | $/MTok out | Context | Max output |
|---------------------|-----------|------------|---------|------------|
| `claude-haiku-4-5`  | $1        | $5         | 200K    | 64K        |
| `claude-sonnet-4-6` | $3        | $15        | 1M      | 64K        |
| `claude-opus-4-8`   | $5        | $25        | 1M      | 128K       |

The runtime model is wired via `init_chat_model` so the `APP_LLM_PROVIDER` / `APP_LLM_MODEL` strings above are
the only change needed to switch tiers — `harness/patterns/model-and-providers.md`.

## Persistence

Local-first by default; the SAME async code runs on both — only the URL changes (`harness/patterns/durability.md`).
**Phase 1 = SQLite + `create_all`** (no alembic); the migration ladder is a `/deploy` concern only.

- Local (DEMO): SQLite via **aiosqlite** — `sqlite+aiosqlite:///./agent.db` (the `APP_DATABASE_URL` default), schema via `create_all`
- Prod (PRODUCTIONISE): PostgreSQL via **asyncpg** — `postgresql+asyncpg://...` (alembic introduced here, not before)
- ORM: async SQLAlchemy 2.0. **NEVER psycopg2** (sync — breaks the async stack).
- Tables: `runs`, `messages`, `spans` (+ domain entities below). The `runs` table carries
  `input_tokens` / `output_tokens` / `cost_usd` / `thread_id` as first-class columns from Phase 1
  (usage/cost accounting — read `usage_metadata` via a type-guarded `.get()`).
- Domain entities: <!-- FILL IN: tables beyond runs/messages/spans, or "none" -->

## Deploy target

- Target: <!-- FILL IN: TBD | Railway | Fly.io | Modal --> (default `TBD` — chosen at PRODUCTIONISE)
- Artifact: portable build (`langgraph build` / `langgraph.json`, Dockerfile) — `harness/patterns/deploy.md`
- Prod ladder: PostgreSQL + Redis (Layer 11 "Deploy & Operate").

## Key libraries (pin CURRENT versions at build time — verify, don't guess)

| Concern             | Library                                  | Notes |
|---------------------|------------------------------------------|-------|
| Web / SSE           | `fastapi`, `uvicorn`                      | async, SSE streaming |
| Orchestration       | `langgraph`, `langchain`, `langchain-core` | StateGraph + ReAct; `init_chat_model` |
| LLM provider SDK    | one of `langchain-anthropic` / `-openai` / `-google-genai` | match the provider above |
| DB (local)          | `sqlalchemy[asyncio]`, `aiosqlite`       | local-first default; the prod driver is a MAIN dep (not dev-only) so tests use it |
| DB (prod)           | `asyncpg`                                | added at PRODUCTIONISE; NEVER psycopg2 |
| Settings            | `pydantic-settings`                      | env prefix `APP_`; `extra='ignore'` + inline-comment/whitespace strip on values |
| Observability       | `opentelemetry-api` / `-sdk`             | OTel-GenAI spans → SQLite; opt-in OTLP export |
| MCP (external only) | `langchain-mcp-adapters` / `mcp`         | EXTERNAL integrations only — see What to avoid |
| Tests               | `pytest`, `pytest-asyncio`               | FakeModel drives the loop with no API key |
| UI E2E (UI builds)  | `pytest-playwright`, `playwright`        | pin for any UI build — gate check 2 runs `tests/e2e/` too, so a missing playwright aborts collection; omit for a headless product |

## What to avoid (load-bearing — do not relitigate; full rationale in `harness/harness.md`)

- **No `psycopg2` / any sync DB driver** — the whole stack is async (aiosqlite / asyncpg only).
- **No MCP for internal tools** — internal tools are plain typed `@tool` in-process. MCP is for EXTERNAL
  integrations only, and with **OAuth 2.1 (no static secrets)** — `harness/patterns/tools-and-mcp.md`.
- **No guessed/old library or model versions** — a stale pin 404s. Verify latest, then pin.
- **No frontier model as the runtime default** — default cheap; upgrade tier only when justified.
- **No Pydantic AI here** — LangGraph is the build target; Pydantic AI is the documented alternative only.
- **No secrets in code** — config via `APP_`-prefixed env / `.env` (pydantic-settings). Secrets are
  `SecretStr`, unwrapped with `get_secret_value()` only at the use boundary, never logged/printed/repr'd.
- **No raw env values trusted as-is** — pydantic-settings does NOT strip inline `#` comments or surrounding
  whitespace, so `sk-xxx # key` silently 401s on the real run while the build is green. Strip both in a
  validator, and set `extra='ignore'` so undeclared `.env` keys (`TEST_DATABASE_URL`, CI vars) don't raise.
  These live in the reused tested core's `config.py`; this file only records the per-build choices that feed it.
