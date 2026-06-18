# Architecture

> **Boilerplate status:** Filled in by the tech-designer sub-agent after the product spec is approved.

---

## System Overview

<!-- FILL IN: One paragraph describing the system at a high level. Who/what interacts with it? -->

## Agentic Stack Layers Used

<!-- Which of the 10 layers in ../engineering/agentic-architecture.md this agent uses. Baseline layers
     are always on; mark each earns-its-place layer yes/no and say why. -->

| Layer | Used? | Why / notes |
|-------|-------|-------------|
| 1 Model | ✅ baseline | <!-- model + routing --> |
| 2 Context | ✅ baseline | |
| 3 Memory — working/short-term | ✅ baseline | |
| 3 Memory — long-term | <!-- yes/no --> | <!-- remembers across sessions? --> |
| 4 Tools / MCP | ✅ baseline | <!-- which MCP servers --> |
| 5 Retrieval / RAG | <!-- yes/no --> | <!-- depends on a knowledge corpus? --> |
| 6 Multi-agent | <!-- yes/no --> | <!-- escalation reason (multi-agent.md) --> |
| 7 Guardrails — action-safety | ✅ baseline | |
| 7 Guardrails — input/output + HITL | <!-- yes/no --> | <!-- untrusted input / irreversible action? --> |
| 8 Durability / checkpointing | <!-- yes/no --> | <!-- long/resumable runs? --> |
| 9 Observability + evals | ✅ baseline | |
| 10 Interface / serving | ✅ | <!-- API / UI / CLI / webhook --> |

## Component Map

<!-- FILL IN: List the major components and what each does. -->

```
[Component A]
    ↓
[Component B]   ←→   [External Service]
    ↓
[Component C]
```

## Layers

<!-- FILL IN: Describe the layers of the system (e.g., API → Agent Loop → Tools → Storage). -->

| Layer | Responsibility |
|-------|----------------|
| <!-- layer --> | <!-- responsibility --> |

## Data Flow

<!-- FILL IN: Walk through the main data flow from trigger to output. -->

1. Trigger: <!-- how does the agent start? (cron, webhook, user input, etc.) -->
2. <!-- step 2 -->
3. <!-- step 3 -->
4. Output: <!-- what does the agent produce? -->

## External Dependencies

<!-- FILL IN: APIs, services, databases the agent depends on. -->

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| <!-- name --> | <!-- what it does --> | <!-- what happens if it's down --> |

## Deployment Model

<!-- FILL IN: How does this run? (local script, cloud function, long-running service, etc.) -->
