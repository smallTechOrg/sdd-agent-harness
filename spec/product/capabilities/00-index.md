# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

DataChat's core loop (Phase 1) is three capabilities; Phase 3 adds a chat UI and chart visualizations.

| # | Capability | File | Phase |
|---|-----------|------|-------|
| 1 | Upload CSV(s) into a dataset | [01-upload-csv-into-dataset.md](01-upload-csv-into-dataset.md) | 1 |
| 2 | Natural-language query over a dataset | [02-natural-language-query.md](02-natural-language-query.md) | 1 |
| 3 | Multi-turn conversation | [03-multi-turn-conversation.md](03-multi-turn-conversation.md) | 1 |
| 4 | Visualizations (charts) | [04-visualizations.md](04-visualizations.md) | 3 (with the UI) |

The Next.js + React + Tailwind chat UI that surfaces these is specced in [`../06-ui.md`](../06-ui.md).

## How to Add a New Capability

Run `/spec-new-capability [description]` or ask the spec-writer directly. The spec-writer will:
1. Create a new file in this directory
2. Update this index
3. Flag any dependencies on existing capabilities
4. The spec-reviewer will validate it fits the architecture

## Capability File Template

Each capability file should answer:
- **What it does** (one sentence)
- **Inputs** (what data it receives)
- **Outputs** (what it produces)
- **External calls** (APIs, LLMs, databases it touches)
- **Error cases** (what can go wrong and how it's handled)
- **Success criteria** (how we test it)
