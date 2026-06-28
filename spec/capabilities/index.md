# Capabilities Index

> One file per discrete capability. Core set for v1 below; deferred capabilities land in later
> phases per [../roadmap.md](../roadmap.md).

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| Dataset ingestion (upload + auto-profile) | [dataset-ingestion.md](dataset-ingestion.md) | 1 |
| Conversational analysis (plan → code → run → answer) | [conversational-analysis.md](conversational-analysis.md) | 1 |
| Conversation memory (contextual follow-ups) | [conversation-memory.md](conversation-memory.md) | 1 |
| Run history (persisted, browsable per dataset) | [run-history.md](run-history.md) | 1 persist / 2 browse |

### Deferred (later phases — see roadmap)

- Interactive charts (P3)
- Live streaming steps + elapsed timer (P3)
- Cost tracking UI (P2; tokens captured from P1)
- Dataset library management (P2)
- Multi-file joins / Excel multi-sheet (P4)
- Column notes & business rules (P4)
- Clarify-vs-best-guess + deep iterative refinement (P4)

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer will add a
`<name>.md` here, update this index, flag dependencies, and self-review fit before returning.
