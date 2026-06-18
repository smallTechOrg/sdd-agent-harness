# Claude Code — Entry Point

A spec-driven boilerplate for building AI agents. The spec in `spec/` is the single source of truth.

## First action every session

1. Read [`spec/engineering/ai-agents.md`](spec/engineering/ai-agents.md) — the rules for every session.
2. Check `spec/product/01-vision.md`: if it still has `<!-- FILL IN -->` markers, the spec isn't ready —
   **don't write application code**; invoke the agent-builder (below). If it's filled in, read the spec
   manifest below, then build.
3. Open a session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`.

## Spec manifest (read in this order when the spec is complete)

```
spec/product/01-vision.md · 02-architecture.md · capabilities/ · 04-data-model.md · 05-api.md · 06-ui.md
spec/product/07-agent-graph.md       ← REQUIRED for any agent-framework project (LangGraph, CrewAI, …)
spec/engineering/agentic-architecture.md  ← the agentic AI stack (10 layers) — read after the product spec
spec/engineering/ai-agents.md · spec-driven.md · phases.md · project-layout.md · tech-stack.md · code-style.md
spec/engineering/patterns/           ← one canonical home per layer:
    react-agent.md · llm-providers.md · memory-and-context.md · tools-and-mcp.md · retrieval.md
    multi-agent.md · guardrails-and-hitl.md · durability.md · observability-and-evals.md
```

`07-agent-graph.md` is mandatory for any orchestration-framework project. If it's missing when you reach
Phase 1, stop and raise it as a blocker. The **default agent ships memory + MCP tools + evals + OTel
tracing, all real in Phase 1** — the raised baseline in `agentic-architecture.md`. Retrieval, long-term
memory, multi-agent, HITL, and durability earn their place in later phases.

## Non-negotiables (full text in `ai-agents.md`)

1. The README must always be accurate — test every command before claiming done.
2. Never claim a test passed without running it.
3. Commit then push, every time — one indivisible action.
4. `main` is boilerplate-only — app code on a feature branch, into `main` via PR only.
5. Agents that act on the outside world use a ReAct loop — see `patterns/react-agent.md`.

## If the spec isn't ready

Invoke the agent-builder: *"Use the agent-builder sub-agent in `.claude/agents/agent-builder.md`"*, or
run `/build [your idea]`.

## Sub-agents

| Agent | Purpose |
|-------|---------|
| `agent-builder` | Master orchestrator — start here for a new build |
| `spec-writer` / `spec-reviewer` | Write / review the product spec |
| `tech-designer` | Propose tech stack and architecture |
| `planner` / `plan-reviewer` | Create / validate the phased plan |
| `qa-auditor` | Test and gate completed phases |
| `drift-auditor` | Audit spec/code drift |

All live in `.claude/agents/`. The canonical project layout is in [`spec/engineering/project-layout.md`](spec/engineering/project-layout.md).
