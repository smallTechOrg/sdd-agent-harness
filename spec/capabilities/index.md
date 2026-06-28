# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

<!-- FILL IN: List capabilities here as they are defined. Each entry links to its spec file (no number prefix). -->

| Capability | File | Phase |
|-----------|------|-------|
| Profile Dataset on Upload | [profile-dataset.md](profile-dataset.md) | 1 |
| Answer a Question with Multi-Step Reasoning | [answer-question.md](answer-question.md) | 1 |
| Stream Live Reasoning Steps | [stream-reasoning.md](stream-reasoning.md) | 1 |
| Per-Dataset Audit History & Cost Tracking | [audit-and-cost.md](audit-and-cost.md) | 1 |

> **Deferred (later phases, not yet capabilities):** persistent dataset library across days (Phase 2); multi-file joins / folder-as-one-dataset (Phase 3).

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
