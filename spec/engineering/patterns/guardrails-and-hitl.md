# Pattern: Guardrails & Human-in-the-Loop

**Canonical home for layer 7 (Guardrails + HITL)**
([`../agentic-architecture.md`](../agentic-architecture.md)). The safety boundary around the loop: what
goes in, what comes out, and which actions a human must approve.

---

## Three guardrail points

```
input  ──▶ [input guardrail] ──▶ orchestrator ──▶ [action guardrail] ──▶ tool/MCP
                                       │
                                       └──▶ [output guardrail] ──▶ user
```

1. **Input guardrails** — validate and bound the user's input before it reaches the model: auth/authz,
   size limits, schema, prompt-injection screening for untrusted content (e.g. retrieved web pages,
   uploaded files). Untrusted text must never be treated as instructions.
2. **Action guardrails** — every model-chosen action is validated before it runs (typed-arg validation,
   least privilege, the AST safe-executor for code). Defined in
   [`tools-and-mcp.md`](tools-and-mcp.md) and [`react-agent.md`](react-agent.md) § Action-safety —
   link, don't restate.
3. **Output guardrails** — validate the final answer before returning it: schema/format, no leaked
   secrets ([`../secret-hygiene.md`](../secret-hygiene.md)), PII handling, and a relevance/groundedness
   check for high-stakes answers.

## Human-in-the-loop (HITL)

Some actions are **irreversible or high-stakes** — send an email, delete data, move money, deploy,
post publicly. These must not fire on model output alone. Pattern:

- The action guardrail **classifies** the proposed action; high-stakes ones **interrupt** the run
  instead of executing.
- The run is **checkpointed** at the interrupt (see [`durability.md`](durability.md)) and surfaces an
  approval request to the user with the action's plain-English `description` and arguments.
- On approve → **resume** from the checkpoint and execute. On reject → feed the rejection back as an
  observation so the loop can replan.

LangGraph's `interrupt()` + checkpointer is the mechanism; the API exposes an approve/reject endpoint
that resumes the graph by `thread_id`.

## What's high-stakes (default policy)

Treat as approval-required unless the spec explicitly downgrades it: external sends (email/Slack/SMS),
writes/deletes to systems of record, payments, deploys/infra changes, anything publicly visible. Pure
reads and the agent's own scratch are auto-approved.

## Phasing

Baseline — the **action guardrail** (typed-arg validation + the action-safety boundary) ships in
Phase 1; the high-stakes classifier exists but passes, since nothing irreversible is live yet. **Input
and output guardrails earn their place** — add input guardrails (prompt-injection screening, size/schema
bounds) when the agent ingests untrusted content, and output guardrails (groundedness, PII) when answers
are high-stakes. Real HITL interrupts earn their place the moment the agent gains a real irreversible
action. Authority: [`../phases.md`](../phases.md) § Agentic layers by phase.
