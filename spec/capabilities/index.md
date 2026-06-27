# Capabilities Index

> One file per capability — each describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs.

## Capabilities in This Project

| Capability | File | Phase | Status |
|-----------|------|-------|--------|
| Upload Dataset | [upload_dataset.md](upload_dataset.md) | 1 | core |
| Answer Question About a Dataset | [answer_question.md](answer_question.md) | 1 | core |
| Visual Summary (Charts) | [visual_summary.md](visual_summary.md) | 2 | deferred — UI stub in Phase 1 |
| Detect Anomalies & Patterns | [detect_anomalies.md](detect_anomalies.md) | 3 | deferred — UI stub in Phase 1 |

Phase 1 ships the two core capabilities (Upload + Answer). The charts and anomaly capabilities appear in Phase 1 only as clearly-labelled non-functional UI stubs, then become real in Phases 2 and 3.

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will create a new `<name>.md`, update this index, flag dependencies, and self-review.

## Capability File Template

Each capability file answers: What it does · Inputs · Outputs · External calls · Business rules · Success criteria.
