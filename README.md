# Spec-driven agent harness

A frontier (mid-2026) spec-driven **harness** that builds, maintains, and deploys a production agentic AI
agent from a short spec. It ships **knowledge, not a frozen app**: precise, copyable pattern recipes that
**Claude Code** uses to **generate fresh code at build time**, pinning current library
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
> separate from Claude Code and defaults to a cheap tier — set it in `spec/tech-stack.md`.

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
harness/generate.py     regenerates the Claude Code front-ends (CLAUDE.md, .claude/agents/, .claude/commands/) from harness/

spec/product.md         why / what / success criteria / domain  ┐
spec/capabilities/*.md  EARS acceptance criteria (feed the evals) │ the 4-file input contract
spec/agent.md           which agentic layers are on               │ you (or /build) fill
spec/tech-stack.md      provider · runtime model · DB · deploy · tools  ┘

.githooks/              mechanical guardrails (secrets, branch rules, harness/ drift)
```

`CLAUDE.md` and `.claude/` (agents + commands) are **generated** from `harness/` — never edit
them by hand. Edit `harness/` and run `python harness/generate.py`.
