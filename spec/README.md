# Spec — Single Source of Truth

This directory is the authoritative specification for this project. All code must match this spec. When spec and code disagree, spec wins — fix the code.

## Status

Check `spec/product/01-vision.md` to see if the spec has been filled in. If it still contains `<!-- FILL IN -->` markers, the spec-writer sub-agent needs to complete it before any application code is written.

## Structure

```
spec/
  product/             ← What the agent does
    01-vision.md       ← Purpose, goals, success criteria
    02-architecture.md ← System design, layers, data flow
    capabilities/      ← One file per discrete capability (00-index.md lists them)
    04-data-model.md   ← Data schema
    05-api.md          ← API surface (REST/GraphQL/CLI/etc.)
    06-ui.md           ← UI requirements (if any)
    07-agent-graph.md  ← Required for any agent-framework project
  engineering/              ← How to build it
    agentic-architecture.md ← The agentic AI stack (10 layers) — the reference architecture
    ai-agents.md            ← Rules for ALL AI coding sessions (the canonical rule list)
    spec-driven.md          ← Spec-first development (why/how)
    phases.md               ← Phased implementation model
    project-layout.md       ← Canonical structure + README requirements
    tech-stack.md           ← Stack defaults + model + per-layer tech source-of-truth
    code-style.md           ← Style and structural rules
    secret-hygiene.md       ← Secret-handling rules
    patterns/               ← One canonical home per stack layer:
                              react-agent · llm-providers · memory-and-context · tools-and-mcp
                              retrieval · multi-agent · guardrails-and-hitl · durability
                              observability-and-evals
    workflows/              ← Repeatable procedures
```

## Governance Rules

1. **Spec first** — no code change without a spec backing it
2. **One fact, one place** — never duplicate facts across spec files; cross-reference with links
3. **Capabilities are atomic** — each file in `product/capabilities/` describes exactly one discrete thing the agent can do
4. **No implementation details in product spec** — `spec/product/` describes WHAT, `spec/engineering/` describes HOW
5. **Update spec before code** — if requirements change, update the spec first, then update the code

## Who Updates the Spec

- **New project:** spec-writer sub-agent drafts, spec-reviewer validates, you approve
- **New capability:** use the `/spec-new-capability` command or ask the spec-writer directly
- **Bug in spec:** any team member can open a PR; spec-reviewer must approve
