# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

Active:

| Capability | File | Phase |
|-----------|------|-------|
| Profile on Upload | [profile-on-upload.md](profile-on-upload.md) | 1 |
| Ask a Question | [ask-question.md](ask-question.md) | 1 |
| Show Its Work | [show-its-work.md](show-its-work.md) | 1 |
| Persistent Dataset Browser | [persistent-dataset-browser.md](persistent-dataset-browser.md) | 2 |

Deferred (later phases — see [`../roadmap.md`](../roadmap.md)): conversation-memory (3), multi-file-join (4), excel-upload + column-notes (5), suggested-followups + clarifying-question gate + daily-cost-tally (6). These ship as labelled non-functional stubs until their phase.

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
