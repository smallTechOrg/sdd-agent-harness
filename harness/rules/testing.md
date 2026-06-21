# Testing & Gates

## Test before claiming done

A unit of work is not done until its tests pass. Tests are everyone's job — but the
**reviewer validates them and holds the highest bar**. Run the full suite before marking
the iteration complete. Show the output.

## Verification is the executable goal

Acceptance tests are the spec written in executable form — the bridge from `spec` (goal)
to `logs` (outcome). The reviewer owns that bridge; the executor implements `src/` to
satisfy it and writes unit tests for its own code.

## Gate law — two gates, at two altitudes

Quality stays high *and* fast by gating at two levels: a cheap gate per **step**, a hard gate
once per **iteration**.

**Step gate (fast, every step):** a step is complete only when ALL hold —
1. Its code is committed and pushed.
2. Its fast gate test passes (<30s) — actually run, output shown.
3. The analyser sees no drift on handoff.

Never wire a dependent step on top of a red step.

**Iteration gate (hard, once, on the converged whole):** the iteration is complete only when
ALL hold —
1. The applicable **hard gates** (below) pass.
2. The working tree is clean and pushed.
3. The session report in `logs/sessions/` reflects completion.
4. The reviewer has signed off (and, for agent-behaviour requirements, the eval gate passed).
5. `spec ↔ src ↔ logs` reconcile — the drift check is clean.
6. The user has accepted the delivered requirement.

Never mark the iteration complete if any hard gate is red.

## The hard gates

The fixed checks the **iteration gate** must satisfy *where applicable* — the planner does not
re-invent these, it selects which apply:

| Gate | Applies when | What it asserts |
|------|--------------|-----------------|
| Offline stub | always (from the scaffold step on) | full unit suite passes with `…_LLM_PROVIDER=stub`, no key, no network |
| Production driver | any DB | tests run on the store you ship (SQLite/DuckDB), not a substitute engine |
| Golden-path smoke | any UI/HTTP surface | walks the primary user journey end-to-end, asserts response **content** |
| Live-server (backend) | any server | `python -m src` starts; `/health` + one real API route return 200 (curl, logged) |
| Live-UI (frontend) | any browser UI | the **UI origin** is started (`npm run start`, not just `npm run build`) and `GET http://localhost:3000/` returns 200 with an **expected rendered DOM string** in the body. `npm run build` passing is necessary, not sufficient — it prerenders, it does not exercise the request path where SSR browser-API crashes ([C-SSR-BROWSER-API]) surface. Curl the **frontend** port, never the backend, for this line. |
| Stub banner | any UI in stub mode | a visible banner marks stubbed output so no viewer mistakes it for real AI |
| Eval threshold | any agent-behaviour change | `evals/` golden cases pass at threshold (see below) |
| README current | the iteration gate | every README command works as written from the stated directory |

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

The scaffold step (Step 0) onward runs fully offline — no real key, no network. Stubs stand in
for external calls; stub mode is visibly labelled in any UI. Test `conftest.py` sets a hard
`ALLOW_MODEL_REQUESTS=False` guard so a misconfigured test *cannot* make a live model call or
burn a key.

## Honest tests

- Test against the **production** data store and drivers, not a convenient substitute.
  Tests that only pass on a different engine do not count as passing.
- The scaffold step onward must run fully offline — no real API key, no network. Stubs
  stand in for external calls; stubbed mode is visibly labelled in any UI so a viewer
  never mistakes a stub for real output.
- A golden-path smoke test walks the primary user journey end-to-end and asserts response
  **content**, not just status codes.
- **No prompt-string theater.** A behavioural criterion's gate may **not** be satisfied by a
  test that only asserts the *prompt text* contains a substring (e.g. `assert "Markdown table"
  in DOMAIN_PROMPT`). Asserting the instruction exists is not asserting the behaviour happens.
  Every behavioural criterion needs a **behavioural test**: drive the path with a stub/fake model
  and assert the *output* satisfies the criterion (the table is in the response; the follow-up
  references a real column). Prompt-substring asserts are allowed only as a *supplement*, never
  as the gate itself. A real run shipped three such tautological gates — green, proving nothing.

