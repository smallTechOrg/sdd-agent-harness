# Capabilities Index

## Capabilities in This Project

| Capability | Phase | File |
|-----------|-------|------|
| CSV Upload and Profile | Phase 1 (real) | [csv_upload_and_profile.md](csv_upload_and_profile.md) |
| NL Query and Answer | Phase 1 (real) | [nl_query_and_answer.md](nl_query_and_answer.md) |
| Multi-File Operations | Phase 2 (stub in Phase 1) | [multi_file_operations.md](multi_file_operations.md) |
| Session and History | Phase 2 (stub in Phase 1) | [session_and_history.md](session_and_history.md) |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning

## What a Capability File Contains

Each capability file answers:
- **What it does** (one sentence)
- **Inputs** (what data it receives, with source and required flag)
- **Outputs** (what it produces and where it goes)
- **External calls** (APIs, LLMs, databases it touches, and failure handling per call)
- **Business rules** (precise, implementation-neutral rules)
- **Success criteria** (testable assertions — each starts with a checkbox)
