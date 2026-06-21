# Reconcile — the closing of the loop

Reconciliation is what makes this harness more than a code generator: the continuous check that
the **outcome** (`logs/`) matches the **goal** (`spec/`), with the **action** (`src/`) as
the thing adjusted. It serves the one objective — minimize the distance between intent and
behavior over time.

## The three truths

- `spec/` — the goal. What the system should be.
- `src/` — the action. What it is, in code.
- `logs/` — the outcome. What it actually does, in reality.

| Drift       | Meaning                          | Correction                               |
|-------------|----------------------------------|------------------------------------------|
| spec ≠ src  | code doesn't implement the goal  | fix `src/` (route to executor)           |
| src ≠ logs  | code doesn't behave as written   | fix `src/` — a bug (route to `fix`)      |
| logs ≠ spec | reality doesn't meet the goal    | fix `src/`, or amend `spec/` if the goal was wrong |

## The analyser is drift-triggered, not scheduled

The analyser holds a **standing observation mandate** but acts on signals. The supervisor
invokes it:

- at every phase gate, and
- opportunistically on material signals — errors, failing/flaky tests, slow generations,
  repeated user frustration in the prompts.

It reads `logs/runtime/`, test and gate results, timings, and the user's own prompts and
history. It represents reality and the user back to the team.

## What it produces

- Findings and reconciliation reports in `logs/analysis/`.
- When the outcome diverges because the **goal** was wrong, a concrete proposed `spec/`
  amendment — for the reviewer and the human to approve. The analyser never silently edits
  the goal.

## Loop control

- **Re-entry** is routed: a pure bug → the `fix` head (debugger); a goal change → intake
  (researcher); a code gap → the executor.
- **Exit (convergence):** the loop closes when `spec ↔ src ↔ logs` agree and the analyser
  has nothing outstanding. Bound the cycles — do not oscillate.
