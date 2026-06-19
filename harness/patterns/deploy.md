# Pattern: Deploy & Operate (Layer 11)

Take the agent from "boots on my laptop" to "runs as a portable artifact at a reachable URL." **Generate
fresh at build time**, pinning the *current* `langgraph-cli`, `uvicorn`, `asyncpg`, and your base image
(verify latest first — a guessed/old version 404s).

First-class, but two-stage: the **deploy artifacts ALWAYS ship** (every build produces a runnable
container + a portable build manifest), and **deploying is the user's choice** (`/deploy`). The demo gate
runs local SQLite; productionise swaps in the Postgres+Redis rung and proves the same suite passes there —
`workflows/gates.md`.

## Two artifacts — pick one (both ship by default)

| Artifact | What it is | When |
|----------|-----------|------|
| **`langgraph.json` + `langgraph build`** | The LangGraph CLI reads the manifest, builds an image that serves the compiled graph with a managed runtime (checkpointer/queue wiring done for you). | Default for a graph-shaped agent — least glue, native LangGraph ops. |
| **Plain `Dockerfile` + `uvicorn`** | Containerize the FastAPI app from `agent/server.py` and run it yourself. | When you want full control of the server, custom routes (`/traces`, domain endpoints), or a host that just wants a container. |

Ship **both**: the `langgraph.json` for the managed path and a `Dockerfile` for the portable path. They
target the same code, so neither is wasted — the host decides which entrypoint to run.

## `langgraph.json` (the build manifest)
Declares the graph, env, and Python deps so `langgraph build` / `langgraph dev` can serve it. Pin versions
in the referenced requirements, not here.
```json
{
  "dependencies": ["."],
  "graphs": { "agent": "./agent/graph.py:build_graph" },
  "env": ".env",
  "python_version": "3.12"
}
```
`langgraph build -t my-agent:latest` produces the image; `langgraph dev` runs it locally with the managed
runtime. The graph entrypoint is the same `build_graph` the ReAct loop compiles — `patterns/react-agent.md`.

## `Dockerfile` (the portable path) — proven shape
Multi-stage, non-root, runs the existing `agent/__main__.py` (uvicorn on `settings.port`, default 8001).
```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install -r requirements.txt          # pin CURRENT versions in requirements.txt (verify first)

FROM base AS run
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY agent/ ./agent/
RUN useradd -m app && chown -R app /app
USER app                                     # never run the agent as root
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/health').status==200 else 1)"
CMD ["python", "-m", "agent"]                # agent/__main__.py -> uvicorn on settings.port
```
The `HEALTHCHECK` hits the same `GET /health -> {"ok": true}` the demo gate uses (`agent/server.py`) — the
orchestrator restarts the container if the agent stops answering.

## The prod ladder — what changes from local
Local-first SQLite is the default and the demo target. Productionise climbs one rung; **the code is the
same, only the env changes** — that is the whole point of the SQLite→Postgres design across `agent/db.py`
and the checkpointer (`patterns/memory.md`).

| Concern | Demo (local) | Productionise |
|---------|--------------|---------------|
| App DB (`runs`, `messages`, `spans`, domain) | `sqlite+aiosqlite:///./agent.db` | `postgresql+asyncpg://…` (**NEVER psycopg2** — sync) |
| Short-term memory (checkpointer) | `AsyncSqliteSaver` | `AsyncPostgresSaver` (asyncpg DSN) — `patterns/memory.md` |
| Run queue / cross-worker coordination | none (single process) | **Redis** — task queue + pub/sub for streaming + locks across replicas |
| Secrets | `.env` (gitignored) | host secret store / injected env — **never in the image, never in the prompt** |
| Observability | spans → local SQLite, viewed at `/traces` | same `spans` table on Postgres; opt-in OTLP export `patterns/observability-and-evals.md` |

Everything is driven by `Settings` (env prefix `APP_`, `agent/config.py`), so the *only* difference between
the rungs is environment variables — flip `APP_DATABASE_URL` and the same image runs on Postgres.

### Redis (the productionise-only rung)
Redis appears only when you outgrow a single process: a durable run queue (long runs survive a restart),
pub/sub to fan `/runs` streaming out to multiple replicas, and distributed locks so two workers don't
double-process a run. The `langgraph` managed runtime wires it for you; on the plain-uvicorn path add it
explicitly. **A single-replica deploy does not need Redis** — don't add it before the load does.

## Secrets — outside the image AND outside the prompt
Two separate rules, both non-negotiable:
- **Out of the image/repo.** `.env` is local-only and gitignored; prod reads secrets from the host's secret
  store, injected as env at runtime. Never `COPY .env` into the image, never bake a key into a layer.
- **Out of the model prompt.** The runtime LLM gets tool *names*, never the credentials behind them —
  `patterns/tools-and-mcp.md` (action-safety boundary). Same key, two leaks to prevent: the layer cache and
  the context window. The `APP_LLM_API_KEY` and any MCP OAuth tokens (`patterns/tools-and-mcp.md`) live in
  `Settings`, read from injected env, used by tool bodies only.

## Migrations — Postgres needs real DDL
`init_db()`'s `create_all` is fine for SQLite-first local dev; on Postgres use a migration tool (e.g.
Alembic, async engine) so schema changes are versioned and reviewable — never auto-`create_all` against a
prod database where a column rename would silently diverge. Generate the first migration from the
`agent/db.py` models at productionise time.

## Hosts (TBD — pick per project, set in `spec/tech-stack.md`)
Deploy artifacts are host-agnostic; the host is a choice, not a default.

| Host | Best for | Shape |
|------|----------|-------|
| **Railway** | **Non-experts (recommended).** | Point it at the repo/`Dockerfile`, add a managed Postgres + Redis plugin, set env vars in the dashboard. Least ops. |
| **Fly.io** | Multi-region / edge, fine-grained control. | `fly.toml` + `fly deploy` the `Dockerfile`; managed Postgres + Upstash Redis. |
| **Modal** | Bursty / GPU / serverless-scale Python. | Wrap the app in a Modal function; scale-to-zero, pay-per-run. |

The mechanical test of a deploy is the same regardless of host: a reachable URL where `GET /health`
returns 200 and a real `POST /runs` completes (`workflows/deploy.md`).

## Scaling — when, not by default
Start single-replica; scale only when traces show real load (`/traces`).
- **Stateless app, state in Postgres/Redis** — every run's truth lives in the DB and checkpointer, so the
  container holds nothing; add replicas behind the host's load balancer. This is *why* the prod rung moves
  state out of the process.
- **Concurrency lives in the event loop** — the app is async end-to-end (no psycopg2); one replica handles
  many concurrent runs. Add replicas for CPU/throughput headroom, not for concurrency.
- **Cheap runtime tier by default** — the product LLM is a cheap model (`spec/tech-stack.md`); the dominant
  cost is tokens, not compute. Keep injected context tight (`patterns/context-engineering.md`) before you
  scale hardware.

## CI is opt-in
Deploy artifacts always ship; **CI does not.** Claude Code builds and runs the gates
locally on demand. If the user wants automation, add a workflow that runs the same gate script
(`workflows/gates.md`) on push and, on green, builds the image and deploys to the chosen host — but the
mechanical truth is the gate script's exit code, never a green CI badge. → `workflows/deploy.md`.

## Gate (prove the deploy — run it, don't trust it)
Productionise is mechanical, not prose (`workflows/gates.md`):
- The image **builds** (`docker build` / `langgraph build`) and **boots**; `GET /health` returns 200.
- The **same test suite passes on Postgres**, not just SQLite — flip `APP_DATABASE_URL` to a throwaway
  Postgres and run the suite (the async stack means no code change). The DB-swap tests reuse the conftest
  create_all/drop_all-per-test fixture (`patterns/react-agent.md` gate harness).
- A real `POST /runs` completes against the deployed URL and its **outcome eval passes** — a 200 with a
  wrong answer fails (`patterns/observability-and-evals.md`).
- `git grep` finds **no secret** in the image context and no key reaches the prompt.

"Done deploying" = the productionise gate script exits 0. → `workflows/gates.md`, `workflows/deploy.md`.
