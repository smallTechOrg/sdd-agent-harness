# Harness — Build a production agent from a spec

How Claude Code turns a one-line idea into a working, deployable agentic AI agent. The repo gives you
four things: a **spec contract** (what to build), **workflows** (how), **mechanical gates** (proof it
works), and precise **pattern recipes** in `harness/patterns/` — proven, copyable code you generate fresh from.

## The spec (what the user provides)
- `spec/product.md` — what it does, success criteria, domain instructions.
- `spec/capabilities/*.md` — one per capability, with EARS acceptance criteria (these feed the eval gate).
- `spec/agent.md` — which agentic layers are on.
- `spec/tech-stack.md` — provider, runtime model (cheap tier by default), DB, deploy target, tools.

## Build
`/build "<idea>"` → intake (4 questions, API key required) → fill the spec → build the agent → demo gate.
The target stack is the frontier baseline: a Deep-Agent ReAct loop on LangGraph, tools (MCP for external
integrations), memory, observability (OTel spans → a built-in `/traces` viewer, no Docker), and evals.
Generate this fresh at build time from the recipes in `harness/patterns/`, pinning current versions — the
recipes carry proven, copyable code, so there is no frozen app to lock you in.

## Two model roles
**Claude Code** builds it. The **product's runtime LLM** is a separate choice (Anthropic / OpenAI / Google)
and defaults to a cheap tier, set in `spec/tech-stack.md`.

## Done = gates pass (mechanical, two-tier)
- **Demo:** server boots, `/health` 200, a real run completes, and the **outcome eval passes** — the agent
  does the task per its EARS criteria (a 200 with a wrong answer fails). Traces visible at `/traces`.
- **Productionise (`/deploy`):** tests also pass on Postgres, a portable artifact builds, reachable URL.

"Done" means the gate script exits 0, not an opinion. → `workflows/gates.md`.

## Keep it honest
- README commands work exactly as written — run them before claiming done.
- Never report a test as passing without running it.
- Work on a `feature/<slug>-<date>` branch into a PR; hooks handle secrets/branch rules.
- A funded `APP_LLM_API_KEY` is required for any real run.

Procedures: `workflows/{build,deploy,maintain,spec-new-capability,gates}.md`. Sub-agents: `agents/`.
