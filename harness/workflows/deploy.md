---
description: Productionise a demo-green agent — same suite on Postgres, portable artifact, reachable URL (the productionise-tier gate).
---

# Workflow: `/deploy` — productionise & ship

Take the agent from "passes the demo gate on my laptop" to "the same suite passes on Postgres, a portable
artifact builds, and a real run completes at a reachable URL." This file is the **procedure**; the recipe
knowledge (artifacts, the prod ladder, Redis, secrets, hosts, scaling) lives in `patterns/deploy.md` —
read it, don't restate it here. Persistence/checkpointer swaps: `patterns/persistence.md`,
`patterns/memory.md`. The gate primitives: `workflows/gates.md`.

**Two-tier reminder.** The demo gate already proved the agent *works* (`workflows/gates.md`). `/deploy` is
the **productionise tier**: it proves the *same code* survives the URL swap and ships as an artifact.
Deploy artifacts always build; **deploying is the user's choice** — run this when the user asks.

## Preconditions (a true blocker stops here)
- The **demo gate exits 0** on this branch — never productionise an agent that doesn't pass locally first.
- Work on the existing `feature/<slug>-<date>` branch (hooks enforce; never `main`).
- A reachable **Postgres** is available for the test swap (a throwaway DB is fine — local container or a
  managed instance). `asyncpg` only, **NEVER `psycopg2`** (`patterns/persistence.md`).
- The deploy **host** is set in `spec/tech-stack.md` (Railway / Fly / Modal — `patterns/deploy.md`). Host
  TBD is fine; the artifact is host-agnostic and the gate is identical regardless.
- A funded `APP_LLM_API_KEY` (the reachable-URL step does a *real* run).

## Steps (in order)

### 1 — Pin current versions, generate the artifacts
Both artifacts ship by default (`patterns/deploy.md`): `langgraph.json` (managed path) and a `Dockerfile`
(portable path), plus `requirements.txt`. **Verify the latest `langgraph-cli`, `uvicorn`, `asyncpg`,
`sqlalchemy`, and your base image, then pin** — a guessed/old version 404s. The `Dockerfile` runs the
existing `agent/__main__.py`; neither artifact changes app code.

### 2 — Swap the DB to Postgres and run the SAME suite
The whole point of the async SQLAlchemy 2.0 design is **one code path** — flip the URL, run the identical
tests. No code change; the conftest create_all/drop_all-per-test fixture (`patterns/persistence.md`) runs
against the real engine.

```bash
# throwaway Postgres for the swap test (skip if you already have one reachable)
docker run -d --name agent-pg -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=agent -p 5432:5432 postgres:16

# run the SAME suite against Postgres+asyncpg — overrides conftest's SQLite default
APP_DATABASE_URL="postgresql+asyncpg://postgres:pw@localhost:5432/agent" pytest -q
```

A green SQLite suite is necessary, **not sufficient** — this step is what makes it sufficient. If anything
references `psycopg2`, a sync session, or blocks the loop, it surfaces here. Fix it in the recipe code, not
with a special test path.

### 3 — Migrations (first time on a non-throwaway Postgres)
`init_db()`'s `create_all` is fine for the throwaway swap test and SQLite-first dev. For a Postgres you
can't drop, generate the first **Alembic** migration from the same `Base.metadata` before deploying —
versioned, reviewable DDL. Procedure and rationale: `patterns/persistence.md` (Migrations).

### 4 — Build & boot the artifact locally
Prove the image builds and boots before pushing it anywhere.

```bash
docker build -t my-agent:latest .            # OR: langgraph build -t my-agent:latest
docker run -d --name agent --env-file .env -p 8001:8001 my-agent:latest
curl -fsS http://localhost:8001/health       # expect {"ok":true}
```

`HEALTHCHECK` hits the same `GET /health` (`agent/server.py`). If `/health` doesn't 200, the deploy is red
— stop. (`.env` is local-only and gitignored; prod injects secrets from the host store — `patterns/deploy.md`.)

### 5 — Deploy to the host & confirm a reachable URL
Push the artifact to the host from `spec/tech-stack.md`; wire the prod env (Postgres `asyncpg` DSN, and
Redis only if multi-replica — `patterns/deploy.md`). Set secrets in the host's store, **never in the image
or the prompt**. Then prove the live URL with a *real* run, not a smoke ping:

```bash
DEPLOY_URL="https://<your-host-url>"
curl -fsS "$DEPLOY_URL/health"                                    # 200 {"ok":true}
curl -fsS -X POST "$DEPLOY_URL/runs" -H 'content-type: application/json' \
     -d '{"goal":"<a real goal from spec/capabilities>"}'         # completes; answer in the response
```

Then open `$DEPLOY_URL/traces` — the run's spans (`invoke_agent`, `chat <model>`, `execute_tool.<name>`)
must render. No visible trace = not done.

## The productionise gate (mechanical — run it, don't trust prose)
"Done deploying" = this script **exits 0**, never an opinion (`workflows/gates.md`, `patterns/deploy.md`).
Each line is a hard check; the first failure aborts.

```bash
#!/usr/bin/env bash
# scripts/gate_deploy.sh — productionise tier. Run from repo root on the feature branch.
set -euo pipefail
: "${PG_URL:?set PG_URL to a Postgres asyncpg DSN}"
: "${DEPLOY_URL:?set DEPLOY_URL to the reachable deployed URL}"
: "${APP_LLM_API_KEY:?a funded key is required for the real run}"

echo "1/5 same suite passes on Postgres (asyncpg, not psycopg2)"
APP_DATABASE_URL="$PG_URL" pytest -q

echo "2/5 artifact builds"
docker build -t my-agent:gate . >/dev/null      # or: langgraph build -t my-agent:gate

echo "3/5 no secret in the image context, no key in the prompt"
! git grep -nIE 'APP_LLM_API_KEY *= *.+|sk-[A-Za-z0-9]|BEGIN [A-Z]+ PRIVATE KEY' -- . ':!*.md'
! grep -RIl "$APP_LLM_API_KEY" agent/ 2>/dev/null | grep . && { echo "key reached source"; exit 1; } || true

echo "4/5 reachable URL: /health is 200"
curl -fsS "$DEPLOY_URL/health" | grep -q '"ok":true'

echo "5/5 real run completes AND its outcome eval passes (200 + wrong answer = FAIL)"
RUN_JSON=$(curl -fsS -X POST "$DEPLOY_URL/runs" -H 'content-type: application/json' \
           -d "${GATE_GOAL:?set GATE_GOAL to a goal with a known-good outcome}")
python -m agent.evals --outcome --from-json "$RUN_JSON"   # exits non-zero if the outcome eval fails

echo "PRODUCTIONISE GATE: PASS"
```

The eval step is OUTCOME (and TRAJECTORY where the capability defines one), fed by the EARS acceptance
criteria — a `200` with the wrong answer **fails** (`patterns/observability-and-evals.md`). The gate is the
same regardless of host (`patterns/deploy.md` § Hosts).

## On red
Don't ship. Most failures are one of: a sync driver slipped in (step 2 — `patterns/persistence.md`), a
secret in the image context (step 3 — `patterns/deploy.md` § Secrets), or the outcome eval failing on the
live URL (step 5 — `patterns/observability-and-evals.md`). Fix the recipe code, re-run the gate, re-deploy.
Report what's red and the one fix — never claim a deploy that the script didn't pass.

## After green
- Open the PR from the `feature/<slug>-<date>` branch into `main` (hooks gate branch/secret rules).
- CI is **opt-in** — if the user wants it, run this same gate script on push (`patterns/deploy.md` § CI).
- Scale only when `/traces` shows real load, not by default (`patterns/deploy.md` § Scaling).
