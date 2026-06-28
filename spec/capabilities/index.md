# Capabilities Index

> One file per discrete capability. Real Phase-1 capabilities are first; deferred capabilities are brief stubs tied to their phase.

## Capabilities in This Project

| Capability | Phase | Status | File |
|-----------|-------|--------|------|
| Ingest dataset (upload + profile-lite) | 1 | Real | [ingest-dataset.md](ingest-dataset.md) |
| Analyze CSV (code-execution loop) | 1 | Real | [analyze-csv.md](analyze-csv.md) |
| Render answer (chart + code + transparency + cost) | 1 | Real | [render-answer.md](render-answer.md) |
| Persistent sessions & conversation memory | 2 | Deferred stub | [persistent-sessions.md](persistent-sessions.md) |
| Dataset profile, follow-ups, cost rollup, streaming, notes, exports, saved datasets, library, DB connect, joins | 2–5 | Deferred stub | [deferred.md](deferred.md) |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer creates `<name>.md`, updates this index, flags dependencies, and self-reviews fit against the architecture and data model.
