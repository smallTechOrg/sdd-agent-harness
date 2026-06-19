---
description: Change a live agent without drift — reconcile spec↔code, edit the spec first, code follows, re-run the gate.
---

<!-- GENERATED from harness/ — do not edit; run `python harness/generate.py` -->

# Workflow: maintain — change a live agent without drift

The change loop for an agent that already passes its gate. **The spec is the source of truth; code
follows the spec; nothing ships green by prose.** Read `harness/harness.md` (the law) first; this file
sequences the loop, it does not restate the rules. Build is `workflows/build.md`; a brand-new capability
is `workflows/spec-new-capability.md`; the gate is `workflows/gates.md`.

Use this loop for: a bug fix, a tweak to a capability's EARS criteria, a domain-prompt change, a model or
provider swap (`spec/tech-stack.md`), a new tool, or turning an agentic layer on/off (`spec/agent.md`).

## The invariant

```
reconcile (drift-auditor)  →  spec authoritative  →  code follows spec  →  delta record  →  re-run gate
```

Never edit code first and backfill the spec. If the running code and the spec disagree, you do not yet
know which is right — **stop and reconcile before changing anything.**

## Loop

1. **Reconcile (drift-auditor).** Before touching anything, run the drift-auditor (`agents/drift-auditor.md`)
   to diff `spec/` against the code for the area you're about to change. Three outcomes:
   - *spec right, code wrong* → the change is a fix; proceed.
   - *code right, spec stale* → first correct the spec to match reality (its own delta record), THEN make
     your change on top. Don't stack a new change on a lie.
   - *both agree* → clean baseline; proceed.
   Resolve drift to zero for the touched area before step 2. → `agents/drift-auditor.md`.

2. **Spec first (authoritative).** Edit the spec to describe the desired end state, not the code:
   - behaviour/acceptance → the capability's EARS line(s) in `spec/capabilities/*.md`
     (`WHEN <trigger> the system SHALL <response>`) — these feed the eval gate, so editing them moves the
     gate with you.
   - what it does / success / domain prompt → `spec/product.md`.
   - provider, runtime model (cheap tier), DB, deploy, tools → `spec/tech-stack.md`.
   - layers on/off → `spec/agent.md`.
   The spec is now the contract for this change. Code that disagrees with it is the bug.

3. **Code follows.** Make the smallest change that satisfies the edited spec, generating from the relevant
   recipe in `harness/patterns/` and pinning **current** library versions (a guessed/old version 404s —
   verify latest before pinning). Front-ends are regenerated via `harness/generate.py`, never hand-edited.
   Touch only what the delta names; no opportunistic refactors riding along.

4. **Delta record (OpenSpec-style).** Append one record per change under `spec/changes/`, named
   `YYYY-MM-DD-<slug>.md`. It captures intent and proof so the next session (and the next auditor) can read
   the *why*, not reverse-engineer the diff. Template:

   ```markdown
   # <slug> — <one-line summary>
   - Date: 2026-06-19
   - Author: <Claude Code / user>
   - Type: fix | capability-edit | prompt | model-swap | tool | layer-toggle

   ## Why
   <the problem or request, in one or two sentences>

   ## Spec delta (authoritative — edited FIRST)
   - <file>: <what changed>            # e.g. capabilities/summarise.md: SHALL cite ≥1 source
   - spec/agent.md: memory off → on    # only if layers changed

   ## Code delta (follows the spec)
   - <module/path>: <what changed, by recipe>   # e.g. agent/tools.py: +@tool fetch_url (tools-and-mcp.md)

   ## Gate
   - tier: demo | productionise
   - result: PASS  exit=0               # paste qa-auditor's verdict line; FAIL is not "done"
   ```

   These records are the agent's changelog and the audit trail drift-auditor checks against. One change,
   one record.

5. **Re-run the gate (mechanical, every change — no exceptions).** A change is **not done until the gate
   exits 0.** Run the tier the change warrants (default demo; productionise for anything that touched the
   deploy path) exactly as `workflows/gates.md` defines, and have qa-auditor confirm the exit code —
   "should still pass" is not a pass. Capture the verdict into the delta record's Gate section.

   ```bash
   # the exit code is the verdict; pipefail + tee preserves it (see agents/qa-auditor.md)
   set -o pipefail
   python -m harness.workflows.gate --tier demo 2>&1 | tee /tmp/gate.out
   echo "GATE_EXIT=${PIPESTATUS[0]}"   # 0 = done; anything else = the change is not done
   ```

   Edited a capability's EARS line? The outcome/trajectory eval now asserts the new behaviour — a green gate
   is your proof the change actually landed, not just that the server still boots. Eval mechanics:
   `harness/patterns/observability-and-evals.md`. Inspect the failing span at `/traces`
   (`chat <model>` / `execute_tool.<name>` / `invoke_agent`) when it goes red.

## Ship it

Same rules as build: work on a `feature/<slug>-<date>` branch into a PR — hooks enforce branch/secret
rules; `main` is boilerplate-only. The delta record and a green gate go in the PR. → `harness/harness.md`.

## Never

Edit code before the spec · skip the drift reconcile and stack a change on stale spec · write a delta
record without a real gate verdict · mark a wrong-answer 200 as done · commit app code to `main` ·
hand-edit a generated front-end · pin a library version you didn't verify.
