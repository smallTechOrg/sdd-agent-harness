# Pattern: Multi-Agent Orchestration

**Canonical home for layer 6's multi-agent topologies**
([`../agentic-architecture.md`](../agentic-architecture.md)). The single-agent ReAct loop is the default
([`react-agent.md`](react-agent.md)); this is what to do when one loop can't keep the task coherent.

---

## Escalation criteria — earn it first

Start with one ReAct loop. **Do not** reach for multi-agent until a single loop demonstrably fails. Real
signals that justify escalation:

- The task has **distinct sub-skills** that need different tools, prompts, or models (e.g. research vs.
  writing vs. code review).
- A single context window can't hold everything and **compaction loses too much**.
- You need **parallelism** — independent subtasks that should run concurrently.
- You need an **independent check** — one agent shouldn't both produce and grade its own work.

If none of these hold, a single loop with good tools and memory is cheaper, faster, and easier to debug.
Multi-agent adds latency, cost, and coordination failure modes — it is not a default.

## Topology — supervisor / worker (the one default)

The boilerplate prescribes a **single topology: supervisor / worker** — a router agent delegates to
specialized workers and integrates their results; the supervisor owns the plan. It covers the common
escalation cases (distinct sub-skills, parallel subtasks, an independent check) without the boilerplate
carrying four patterns it rarely needs.

Planner–executor, evaluator–optimizer, and a separate reflection agent are **variations a project can
adopt when its spec calls for them** — but they are not part of the default; record the choice in
`02-architecture.md`. (Reflection — the agent critiquing and revising its own output — is usually best
done as a same-agent step in the single ReAct loop, no second agent needed.)

In LangGraph the supervisor and workers are subgraphs/nodes wired into the parent `StateGraph` — not
separate processes.

## Sub-agent state — shared

Sub-agents **share the run's state** (working memory / `action_history`) rather than each getting an
isolated scope. This keeps the supervisor and workers coherent — every agent sees the same evolving
picture, and there's no contract-marshalling boilerplate between them.

- The supervisor holds the master plan + integrated results in the shared state.
- Workers read the shared context and write their results back to it.
- Usage (tokens/cost) from every sub-agent **rolls up** to the parent run — see
  [`observability-and-evals.md`](observability-and-evals.md).

> ⚠ **Caution:** shared state trades isolation for coherence. The risk is cross-talk — a worker acting
> on another's half-finished scratch. Mitigate by giving each worker a clear task framing and bounding
> **total** work (the global step budget below), so shared state can't fuel a runaway loop.

## Guards still apply

Every sub-agent is a ReAct loop and keeps all the mandatory mechanics from
[`react-agent.md`](react-agent.md): max-iterations → `force_finalize`, the action-safety boundary,
self-correction. A multi-agent system without per-agent iteration guards can loop unboundedly across
agents — bound the **total** work (a global step budget), not just each loop.

## Phasing

Baseline — a single ReAct loop (reflection available as a same-agent quality step); the supervisor /
worker topology earns its place only when an escalation criterion above is met and recorded in
`02-architecture.md` § Agentic stack layers used. Authority: [`../phases.md`](../phases.md) § Agentic
layers by phase.
