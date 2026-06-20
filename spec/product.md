# Product

> Filled by the **spec-writer** from intake. Part 1 of the 4-part spec contract (see `harness/harness.md`).
> Leave the `<!-- FILL IN -->` markers until the spec-writer completes them. This file is the **intent of
> record** for the domain: the spec is truth here. (The reused tested core is truth in its own zone — see
> `spec/constitution.md` § two-zone model.) Every success criterion below must map to **≥1 capability** in
> `spec/capabilities/`; the analyze pre-flight fails the build if any criterion has no capability.

## What it does
<!-- FILL IN: one paragraph — what the agent does, who uses it, the problem it solves. Plain language a
non-technical owner recognizes as their idea; no stack words. -->

## Success criteria (these feed the outcome eval — keep them testable)
<!-- FILL IN: 3–5 measurable outcomes that prove the agent works. Each MUST be provable by the agent giving
the right answer over HTTP — not "documented," but demonstrated. Tag each with the capability that proves it
(→ <slug>); the analyze pre-flight enforces that every criterion has at least one. The P1 capability's
criterion is the one verified live by the outcome eval in v1; P2/P3 criteria are proven against their
registered stub contract until promoted. -->
- [ ] <!-- criterion 1 --> (→ <capability-slug>)
- [ ] <!-- criterion 2 --> (→ <capability-slug>)
- [ ] <!-- criterion 3 --> (→ <capability-slug>)

## Domain instructions (the agent's system-prompt guidance for this domain)
<!-- FILL IN: how the agent should behave in this domain — tone, grounding rules, what to refuse/avoid.
These become the domain system prompt the core assembles each turn (refreshed every turn — never stale). -->

## Out of scope (Future Phases)
<!-- FILL IN: explicit exclusions to prevent scope creep. v1 ships the thinnest real slice (one P1 capability
live); name here anything a reader might assume is in v1 but is deferred or stubbed. -->
