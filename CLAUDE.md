<!-- GENERATED from harness/ — do not edit; run `python harness/generate.py` -->

# Claude Code — Entry Point

**First action: read [`harness/harness.md`](harness/harness.md)** — the operating manual. Then read the
spec in `spec/` if it is filled in; otherwise run `/build "<your idea>"`.

## What this repo is
A frontier spec-driven harness that builds a production agentic AI agent from a spec. Claude Code generates
the agent fresh from the recipes in `harness/patterns/` (current library versions), gated by mechanical
checks. Nothing is a frozen app — the harness ships knowledge, not lock-in.

## Map
- `harness/harness.md` — the rules · `harness/workflows/` — procedures (/build, /deploy, …)
- `harness/agents/` — sub-agent roles · `harness/patterns/` — the frontier code recipes (all 11 layers)
- `.claude/agents/` — those roles as Claude Code subagents · `.claude/commands/` — those workflows as slash commands
- `spec/` — the 4-file input contract you fill · `.githooks/` — mechanical guardrails

A funded `APP_LLM_API_KEY` is required for a real run.
