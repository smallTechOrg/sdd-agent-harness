# Data Model

> **Boilerplate status:** Filled in by the tech-designer sub-agent after architecture is approved.

---

## Storage Technology

<!-- FILL IN: What database/storage does this project use and why? -->

## Baseline agentic entities (start here, then add domain entities)

The raised baseline (`../engineering/agentic-architecture.md`) assumes the **baseline** tables exist in
Phase 1 alongside the agent's domain entities. The earns-its-place tables are added with the layer that
needs them. Timestamps are **naive UTC** (`datetime.utcnow()` — no tzinfo); store UTC, format at the edge.

| Entity | Holds | Layer | When |
|--------|-------|-------|------|
| `runs` | one agent invocation: status, usage (tokens/cost), error, timestamps | 6/9 | **baseline (Phase 1)** |
| `messages` | conversation turns per session (`thread_id`) | 3 (short-term) | **baseline (Phase 1)** |
| `eval_results` | eval run scores per dataset case | 9 | baseline if evals persist scores; else with the eval suite |
| `memory_records` | long-term memory: content, kind, salience, embedding | 3 (long-term) | earns its place (long-term memory) |
| `embeddings` / vector table | chunk vectors + source metadata for retrieval | 5 | earns its place (retrieval/RAG) |

## Entities

<!-- FILL IN: One section per major entity. -->

### Entity: <!-- Name -->

<!-- FILL IN: What does this entity represent? -->

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | <!-- type --> | yes | Primary key |
| <!-- field --> | <!-- type --> | <!-- yes/no --> | <!-- description --> |

### Relationships

<!-- FILL IN: How do entities relate to each other? -->

## Data Lifecycle

<!-- FILL IN: When is data created, updated, and deleted? Is anything time-boxed or archived? -->

## Sensitive Data

<!-- FILL IN: What fields contain PII or secrets? How are they protected? -->
