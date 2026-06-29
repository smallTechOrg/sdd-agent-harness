# Capabilities Index

> One file per capability — exactly one discrete thing the agent can do.

---

## Capabilities in This Project

| Capability | Phase | Status | File |
|-----------|-------|--------|------|
| Analyze question (ask → answer + exact SQL) | 1 | **ACTIVE (Phase 1 core path)** | [analyze_question.md](analyze_question.md) |
| Profile dataset on upload | 2 | DEFERRED | [profile_dataset.md](profile_dataset.md) |
| Render auto-chosen chart | 2 | DEFERRED | [render_chart.md](render_chart.md) |
| Summarize result as a table | 2 | DEFERRED | [summarize_result.md](summarize_result.md) |
| Suggest follow-up questions | 2 | DEFERRED | [suggest_followups.md](suggest_followups.md) |
| Manage session / conversation memory | 3 | DEFERRED | [manage_session_memory.md](manage_session_memory.md) |
| Multi-dataset compare / join query | 3 | DEFERRED | [multi_dataset_query.md](multi_dataset_query.md) |
| Data notes about a dataset | 3 | DEFERRED | [data_notes.md](data_notes.md) |
| Cost tracking + expensive-query warning | 3 | DEFERRED | [cost_tracking.md](cost_tracking.md) |
| Audit trail (browse run history) | 3 | DEFERRED | [audit_trail.md](audit_trail.md) |
| Excel ingest | 3 | DEFERRED | [excel_ingest.md](excel_ingest.md) |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer creates `<name>.md`, updates this index, flags dependencies, and self-reviews fit against the architecture and data model.
