# Spec-driven agent harness

A frontier (mid-2026) spec-driven **harness** that builds, maintains, and deploys a production agentic AI
agent from a short spec. It ships **knowledge, not a frozen app**: precise, copyable pattern recipes that a
coding agent (like Claude Code) uses to **generate fresh code at build time**, pinning current library
versions.

The target is a Deep-Agent ReAct loop on LangGraph (planning todos, sub-agents with isolated context,
scratchpad memory) behind async FastAPI + SSE, with typed in-process tools (MCP for external integrations),
memory, OTel-shaped observability rendered by a built-in `/traces` viewer (no Docker), and outcome +
trajectory evals run as a mechanical gate.

## Start

Open this repo in Claude Code and run:

```
/build "<your idea>"
```

Intake asks four questions, fills the 4-file spec, builds the agent, and stops at the demo gate.

> A funded **`APP_LLM_API_KEY`** is required for any real run (intake checks for it). The runtime LLM is
> separate from the coding agent and defaults to a cheap tier — set it in `spec/tech-stack.md`.

## The current build — DataChat

This repo currently contains a built agent: **DataChat** — upload CSV/JSON into a dataset, ask questions in
plain English, get answers grounded in **read-only SQL** (DuckDB) with a chat UI and a `/traces` viewer.
Spec in [`spec/`](spec/), plan in `reports/implementation-plan.md`. Phase 1 is demo-gate green.

```bash
# 1. deps (a funded APP_LLM_API_KEY must be in .env — google_genai / gemini-2.5-flash)
uv pip install -r requirements.txt
npm --prefix ui install

# 2. the demo gate — done = exit 0 (boots, /health, a real run, outcome+trajectory eval, traces)
make gate

# 3. run it
make seed                     # seed a "Demo Sales" dataset to query
make serve                    # agent API + /traces on http://localhost:8001
make ui                       # chat UI on http://localhost:3000  (separate terminal)

make test                     # offline unit suite (FakeModel loop, read-only guardrail, ingest) — no key
```

Endpoints: `GET /health` · `POST /runs {goal, dataset_id?}` · `POST /datasets` · `POST /datasets/{id}/files`
· `GET /datasets/{id}` · `GET /traces`. Layers ON and the phase plan (charts → multi-turn → productionise)
are recorded in [`spec/agent.md`](spec/agent.md) and the implementation plan.

## Everything else

Read **[`harness/harness.md`](harness/harness.md)** — the operating manual (the spec contract, workflows,
the two model roles, and what "done" means). It points to the rest.

## Layout

```
harness/harness.md      the rules — read this first
harness/workflows/      procedures: /build, /deploy, /maintain, /spec-new-capability
harness/agents/         sub-agent roles (spec-writer, planner, qa-auditor, …)
harness/patterns/       the frontier code recipes — all 11 layers (react-agent, tools-and-mcp,
                        persistence, observability-and-evals, deploy, …)
harness/generate.py     regenerates the host front-ends (CLAUDE.md, AGENTS.md, .claude/) from harness/

spec/product.md         why / what / success criteria / domain  ┐
spec/capabilities/*.md  EARS acceptance criteria (feed the evals) │ the 4-file input contract
spec/agent.md           which agentic layers are on               │ you (or /build) fill
spec/tech-stack.md      provider · runtime model · DB · deploy · tools  ┘

.githooks/              mechanical guardrails (secrets, branch rules, harness/ drift)
```

`CLAUDE.md`, `AGENTS.md`, `.claude/`, and `.github/agents/` are **generated** from `harness/` — never edit
them by hand. Edit `harness/` and run `python harness/generate.py`.
