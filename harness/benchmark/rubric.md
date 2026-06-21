# Benchmark Rubric — speed × quality

A run is scored on both axes. **Pass = clears every quality-floor item AND every speed target.**
Speed gained by skipping a quality item is a fail, not a win.

---

## Speed (from the session report's Run telemetry)

All times are wall-clock, sourced from the per-stage start/end timestamps (non-negotiable #12).

| Metric | Target | Stretch |
|--------|--------|---------|
| Brief → FR approved | ≤ 3 min | ≤ 90 s |
| FR approved → Step 0 green (`/health` 200) | ≤ 5 min | ≤ 2 min |
| Brief → iteration delivered (user-testable) | ≤ 30 min | ≤ 15 min |
| Human round-trips | ≤ 2 (intake + acceptance) | 1 |
| Parallel-step front (max steps in flight at once) | ≥ 3 | ≥ 5 |

Also record, for diagnosis (no target, just trend): total turns, total tokens, slowest single
step, and the critical-path length (longest dependency chain in the step DAG).

## Quality (the floor — every item must hold)

| Item | Pass condition |
|------|----------------|
| Spec gate | FR passed the pre-code reviewer gate with no unresolved `[NEEDS CLARIFICATION]` |
| Iteration hard-gate | the full [testing.md](../rules/testing.md) hard gates passed on the converged whole |
| First-pass review | iteration gate passed on the **first** reviewer pass (a re-bounce counts against quality) |
| Evals | agent-behaviour evals passed at threshold (binary PASS/FAIL) |
| Production driver | tests ran on the shipped store (SQLite/DuckDB), not a substitute |
| README true | every README command works as written from the stated directory |
| Drift clean | `spec ↔ src ↔ logs` reconcile; tracker matches `logs/` |
| No carry-forward | no defect deferred a second time; no dead code left unsequenced |
| Capability coverage | every capability named in the brief is demonstrable in the running app |

## Score

- **Speed score:** count of speed metrics meeting Target (out of 5).
- **Quality score:** PASS only if **all** floor items hold; otherwise FAIL + the failing items.
- **Run verdict:** PASS iff Quality = PASS and Speed ≥ 4/5 at Target.

Record both raw numbers and the verdict in [results.md](results.md) — the raw numbers are what
reveal the dominant cost (tooling vs model-latency vs rework) and thus what to optimise next.
