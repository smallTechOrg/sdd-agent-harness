# Claude Code — Entry Point

This is a spec-driven AI agent boilerplate. Read this file first, then follow the instructions below.

## What This Repo Is

A starting template for building AI agents. The spec in `spec/` is either:
- **Partially or fully filled in** — you are implementing an agent from a completed spec
- **Empty / placeholder** — you are in the build phase; run `/zero-shot-build` to drive the spec and build

## Your First Action Every Session

1. Read `harness/rules/ai-agents.md` — mandatory rules for all AI sessions
2. Check whether `spec/roadmap.md` has been filled in:
   - If it still contains `<!-- FILL IN -->` placeholders → the spec is not ready; do not write application code yet
   - If it is filled in → proceed to read the full spec manifest below before touching any code
3. Open a session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`

## Spec Manifest (read in this order when spec is complete)

```
spec/roadmap.md
spec/architecture.md
spec/capabilities/          ← all files
spec/data.md
spec/api.md
spec/ui.md
spec/agent.md     ← REQUIRED for any agent framework project
harness/rules/ai-agents.md
harness/patterns/spec-driven.md
harness/patterns/phases.md
harness/patterns/project-layout.md
harness/patterns/engineering-practices.md
harness/patterns/test-driven.md
harness/patterns/ui-ux.md
harness/patterns/tech-stack.md     ← generic stack rules (chosen stack is in spec/architecture.md)
harness/patterns/code.md           ← generic code conventions
harness/patterns/agentic-ai.md     ← catalogue of agentic patterns (chosen graph is in spec/agent.md)
harness/rules/git.md
```

**`spec/agent.md` is mandatory** for any project using LangGraph, CrewAI, AutoGen, or any agent orchestration framework. If it does not exist when you reach Phase 2, stop and raise it as a blocker. (The reusable catalogue of agentic-AI patterns to choose from lives in `harness/patterns/agentic-ai.md`.)

## If the Spec Is Not Ready

Tell the user to run **`/zero-shot-build [their idea]`**. That skill runs one intake round — the only interactive step. It may ask additional clarifying questions, and asks the user to fill `.env` with the required API keys/secrets. Once intake completes, the **agent-builder** orchestrator runs design → scaffold → build → ship autonomously to a perfectly-working, thoroughly-tested agent, with zero further user interaction.

## Skills (entry points)

These are the entry points. All are manual (`disable-model-invocation: true`). Each is invocable as a skill **and** as a slash command (`.claude/commands/<name>.md` defers to the skill — the skill is the source of truth, so the two never drift).

| Skill / command | Purpose |
|-----------------|---------|
| `/zero-shot-build [idea]` | Idea → working, verified skeleton (drives the agent-builder). Also adds a new capability. |
| `/zero-shot-fix [target]` | Diagnose + fix a bug, error, failing test, or spec/code drift, then verify. |
| `/zero-shot-sync [scope]` | Reconcile spec ↔ code so they match (spec wins), then verify. |

## Key Rules (summary — full rules in harness/rules/ai-agents.md)

- Never write application code before reading the full spec
- Never skip a phase — complete phase N before starting phase N+1
- Commit every logical unit of work; never let the working tree stay dirty
- Update `reports/sessions/` at the start and end of every session
- Tests and evals run against the real LLM/API using keys from `.env` — never gate the build on offline/stubbed runs
- When in doubt, ask at intake — do not guess requirements; once intake completes, build autonomously without further prompts

## Sub-agents (the team)

`/zero-shot-build` delegates a full build to **agent-builder**, which coordinates the rest and owns git/PR. `/zero-shot-fix` and `/zero-shot-sync` call the workers directly (no agent-builder) and own git themselves. Each agent is one full, self-contained definition at `.claude/agents/<name>.md` (the path is the agent slug).

| Agent | Role | Tools |
|-------|------|-------|
| agent-builder | Orchestrator — coordinates the team and owns the git/PR surface for a build | read/bash/agent |
| spec-writer | Write the product spec **and** self-review it | read/write |
| tech-architect | Design **and** review stack/architecture/agent/plan | read/write |
| code-generator | Write code + tests for one phase / one fix | read/write/bash |
| qa-auditor | Independent code review **and** run gates/tests/app **and** audit spec↔code drift | read-only (bash) |

Pattern: maker → checker on the highest-stakes surface — code-generator writes, **qa-auditor** independently reviews it (logic/security/spec-fidelity) *and* runs the gates. spec-writer and tech-architect each self-review (design altitude is lower-risk). agent-builder orchestrates and owns git; qa-auditor never edits.
