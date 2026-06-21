# Workflow: Fix

`analyser → planner → executor → reviewer → deployer → analyser ↺`

The fix workflow handles a known bug or regression. The analyser leads — it has already
observed the failure in `logs/` and brings a diagnosis. The tail (planner → deployer) is
shared with the build workflow.

---

## When to use

- A gate test is failing or flaky
- Runtime logs show an error or unexpected behaviour
- The analyser has flagged a `src ≠ logs` drift (code doesn't behave as written)

If the root cause turns out to be a goal change (the spec was wrong), re-enter via the
**build** workflow at the researcher stage instead.

---

## Stages

### 1. analyser — diagnose

Reads `logs/runtime/`, the failing test output, and the session report. Produces a
diagnosis: what is broken, where, and why. Routes to the planner with a scoped brief.

### 2. planner — scope the fix

Slices the fix into the smallest change that restores the gate. Records the fix plan in
the session report.

### 3. executor — make the fix

Implements the fix in `src/`. No scope creep — only what the diagnosis calls for.

### 4. reviewer — confirm the fix

Verifies the fix addresses the root cause (not just the symptom). Confirms the gate test
passes. Signs off before deploying.

### 5. deployer — re-ship

Re-deploys the corrected build.

### 6. analyser — confirm closure

Re-reads `logs/` after the fix. Confirms `src ↔ logs` reconcile. Exits if resolved;
loops if new drift appears.
