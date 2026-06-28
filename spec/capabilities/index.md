# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| Analyze Question (core) | [analyze_question.md](analyze_question.md) | 1 |
| Profile Dataset | [profile_dataset.md](profile_dataset.md) | 2 |
| Suggest Follow-ups | [suggest_followups.md](suggest_followups.md) | 2 |
| Interactive Charts | [interactive_charts.md](interactive_charts.md) | 3 |
| Persistent Library, History & Memory | [persistent_library_history.md](persistent_library_history.md) | 4 |
| Multi-File Analysis | [multi_file_analysis.md](multi_file_analysis.md) | 4 |

The single core capability is **Analyze Question** (Phase 1); the rest are deferred and stubbed-and-labelled in Phase 1 (see [`../roadmap.md`](../roadmap.md#phases-of-development) and [`../ui.md`](../ui.md)).

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning

## Capability File Template

Each capability file should answer:
- **What it does** (one sentence)
- **Inputs** (what data it receives)
- **Outputs** (what it produces)
- **External calls** (APIs, LLMs, databases it touches)
- **Error cases** (what can go wrong and how it's handled)
- **Success criteria** (how we test it)
