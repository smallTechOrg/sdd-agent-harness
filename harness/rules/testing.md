# Testing & Gates

## Test before claiming done

A unit of work is not done until its tests pass. Tests are everyone's job — but the
**reviewer validates them and holds the highest bar**. Run the full suite before marking
a phase complete. Show the output.

## Verification is the executable goal

Acceptance tests are the spec written in executable form — the bridge from `spec` (goal)
to `logs` (outcome). The reviewer owns that bridge; the executor implements `src/` to
satisfy it and writes unit tests for its own code.

## Gate law

Each iteration ends at a gate. It is complete only when ALL hold:

1. All code for the iteration is committed and pushed.
2. The iteration's gate test passes — actually run, output shown.
3. The applicable **hard gates** (below) pass.
4. The working tree is clean.
5. The session report in `logs/sessions/` reflects completion.
6. The reviewer has signed off (and, for agent-behaviour iterations, the eval gate passed).
7. `spec ↔ src ↔ logs` reconcile — the drift check is clean.

Never mark an iteration complete if any gate is red. Never start the next iteration first.

## The hard gates

The fixed checks an iteration's gate must satisfy *where applicable* — the planner does not
re-invent these, it selects which apply:

| Gate | Applies when | What it asserts |
|------|--------------|-----------------|
| Offline stub | always (from the skeleton iteration on) | full unit suite passes with `…_LLM_PROVIDER=stub`, no key, no network |
| Production driver | any DB | tests run on the store you ship (SQLite/DuckDB), not a substitute engine |
| Golden-path smoke | any UI/HTTP surface | walks the primary user journey end-to-end, asserts response **content** |
| Live-server | any server | `python -m src` starts; `/health` + one real page return 200 (curl, logged) |
| Stub banner | any UI in stub mode | a visible banner marks stubbed output so no viewer mistakes it for real AI |
| Eval threshold | any agent-behaviour change | `evals/` golden cases pass at threshold (see below) |
| README current | final iteration | every README command works as written from the stated directory |

## Evals — behaviour, not just plumbing

Seed `evals/` with ~20 golden cases (input + approved output) drawn from **real failures**,
a threshold config, and a runner so the *identical* eval runs locally, at the gate, and in
CI. Choose the evaluator by failure mode:

- **Code-based / exact-match** for anything code can verify — offline, no key, every commit.
- **LLM-as-judge** only for subjective dimensions, only after calibrating to ~75–90% human
  agreement, scored **binary PASS/FAIL + critique** (never a 1–5 Likert).

Track cheap trajectory signals every run: turn count, tool-call count, tokens. A green stub
run proves coverage; the eval gate proves correctness. Don't over-collect — a small set from
real failures beats a large synthetic suite.

## Offline is enforced, not hoped

The skeleton (first) iteration runs fully offline — no real key, no network. Stubs stand in
for external calls; stub mode is visibly labelled in any UI. Test `conftest.py` sets a hard
`ALLOW_MODEL_REQUESTS=False` guard so a misconfigured test *cannot* make a live model call or
burn a key.

## Honest tests

- Test against the **production** data store and drivers, not a convenient substitute.
  Tests that only pass on a different engine do not count as passing.
- The skeleton (first) phase must run fully offline — no real API key, no network. Stubs
  stand in for external calls; stubbed mode is visibly labelled in any UI so a viewer
  never mistakes a stub for real output.
- A golden-path smoke test walks the primary user journey end-to-end and asserts response
  **content**, not just status codes. 

