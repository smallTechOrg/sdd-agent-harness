# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

These are the Phase-1 (core-loop) capabilities. Later-phase features (conversation memory, auto-insights, live DB source, agentic resilience) become capabilities as their phases land — see [../roadmap.md](../roadmap.md).

| Capability | File | Phase |
|-----------|------|-------|
| Upload and Profile | [upload-and-profile.md](upload-and-profile.md) | 1 |
| Ask a Question, Get an Answer | [ask-question-get-answer.md](ask-question-get-answer.md) | 1 |
| Auto-Chart | [auto-chart.md](auto-chart.md) | 1 |

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
