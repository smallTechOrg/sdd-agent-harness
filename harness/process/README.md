# Process

## Agents

A `supervisor` (the primary agent) coordinates a team of specialist agents, each scoped to
exactly the tools and artefacts it owns.

| Agent | Role |
|-------|------|
| [supervisor](agents/supervisor.md) | Primary session — coordinates the pipeline, owns the human channel |
| [researcher](agents/researcher.md) | Elicits requirements, authors the spec |
| [planner](agents/planner.md) | Slices the iteration into a parallel step DAG |
| [executor](agents/executor.md) | Implements one step in `src/` (many run in parallel) |
| [reviewer](agents/reviewer.md) | Guards verification, signs off the iteration gate |
| [deployer](agents/deployer.md) | Ships demos locally, manages deployment |
| [analyser](agents/analyser.md) | Observes logs, detects drift, closes the loop |

## Workflows

A build runs as a **staged pipeline inside an iterative loop**. The supervisor runs
the pipeline; the analyser closes the loop.

```
            ┌──────────────────────── loop on drift ────────────────────────┐
            ▼                                                                │
researcher ─▶ planner ─▶ executor ─▶ reviewer ─▶ deployer ─▶ analyser ──────┘
```

The pipeline head differs per workflow; the tail is shared:

| Workflow | Pipeline (↺ loops on drift) | Detail |
|----------|------------------------------|--------|
| **Build** | researcher → planner → executor → reviewer → deployer → analyser ↺ | [workflows/build.md](workflows/build.md) |
| **Fix** | analyser → planner → executor → reviewer → deployer → analyser ↺ | [workflows/fix.md](workflows/fix.md) |
| **Deploy** | planner → executor → reviewer → deployer → analyser ↺ | [workflows/deploy.md](workflows/deploy.md) |
