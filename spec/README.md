# Spec — Single Source of Truth

This directory is the authoritative specification for this project. All code must match this spec. When spec and code disagree, spec wins — fix the code.

## Status

Check `spec/vision.md` to see if the spec has been filled in. If it still contains `<!-- FILL IN -->` markers, the spec-writer sub-agent needs to complete it before any application code is written.

## Structure

```
spec/                 ← What the agent does (the product spec)
  vision.md        ← Purpose, goals, success criteria
  architecture.md  ← System design, layers, data flow
  data-model.md    ← Data schema
  api.md           ← API surface (REST/GraphQL/CLI/etc.)
  ui.md            ← UI requirements (if any)
  agentic-ai.md   ← Agent orchestration graph
  capabilities/       ← One file per discrete capability
  tech-stack.md       ← Language, framework, libraries
  code-style.md       ← Style and structural rules

harness/              ← How to build it (the engineering harness)
  ai-agents.md        ← Rules for ALL Claude Code sessions
  spec-driven.md      ← Spec-first development rule
  phases.md           ← Phased implementation model
  project-layout.md   ← Repo layout rules
  secret-hygiene.md   ← Secret-handling rules
  workflows/          ← Repeatable procedures
```

## Governance Rules

1. **Spec first** — no code change without a spec backing it
2. **One fact, one place** — never duplicate facts across spec files; cross-reference with links
3. **Capabilities are atomic** — each file in `capabilities/` describes exactly one discrete thing the agent can do
4. **No implementation details in product spec** — `spec/` describes WHAT, `harness/` describes HOW
5. **Update spec before code** — if requirements change, update the spec first, then update the code

## Who Updates the Spec

- **New project:** the `/zero-shot-build` skill drives the spec-writer sub-agent, which drafts and self-reviews the spec
- **New capability:** run `/zero-shot-build` on an existing spec — it adds the capability via the spec-writer
- **Drift between spec and code:** run `/zero-shot-sync` to reconcile (spec wins)
