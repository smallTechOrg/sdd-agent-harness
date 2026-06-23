# Test-Driven Development

How tests are written in this repo. This expands the Testing section of `engineering-practices.md` into a concrete discipline. It applies to every phase and every fix.

---

## The Loop

**Red → Green → Refactor.** For every behaviour:

1. **Red** — write a failing test that describes the behaviour you want. Run it; watch it fail for the *right reason* (assertion failure, not import error).
2. **Green** — write the minimum code to make it pass. No more.
3. **Refactor** — clean up code *and* test, with the green bar as your safety net. Re-run.

If you wrote code before its test, you skipped Red. Delete the test you wrote afterward, or treat it as a characterization test and label it as such — don't pretend it was TDD.

---

## Test-First Is Not Negotiable for New Behaviour

- A new capability starts with a test that fails because the capability doesn't exist yet.
- A bug fix starts with a **regression test that reproduces the bug** — it must fail on the current code, then pass after the fix. A fix with no failing-first test is unverified; you cannot prove it fixed anything.
- `/zero-shot-fix` follows this: reproduce → red test → fix → green → verify the rest of the suite still passes.

---

## What a Good Test Asserts

- **Behaviour, not implementation.** Assert what the function returns or what side-effect occurred — never which internal helpers were called. Tests that mirror the code break on every refactor.
- **One concept per test, named as a sentence** stating precondition and outcome — so a failure tells you exactly what broke: `test_validate_rejects_negative_threshold`, not `test_validation`.
- **Arrange / Act / Assert**, visibly separated. Setup at top, one action, then assertions — never interleaved.

---

## Determinism Is a Hard Requirement

A flaky test is worse than no test — it trains everyone to ignore red.

- **No wall clock.** Inject time (a `clock` parameter, a frozen-time fixture). Never assert against `now()`.
- **No randomness.** Seed it, or pass the value in. A test that fails 1-in-50 runs is a defect.
- **Determinism at the unit level.** Pure unit tests inject time/seeds and may stub the provider boundary. Integration and E2E tests DO call the real LLM/API (keys from `.env`); for those, assert on response shape/invariants (status, key fields, structure) and tolerate non-deterministic prose rather than exact strings.
- **No shared mutable state between tests.** Each test sets up and tears down its own world. Order-dependence is a bug.

---

## If a Stub Is Used, Don't Mock

For pure-unit isolation, prefer a thin real implementation (in-memory queue, fake repository, stub LLM provider) over a framework mock. Integration and E2E tests use the **real provider**, not a stub.

- Stubs **compose** and survive refactors; mocks encode call sequences and break on them.
- IF a stub LLM provider is used (unit tests or optional offline dev), it should produce **distinct, node-tagged output** (see `rules/ai-agents.md` rule 8) so it is credible and node cross-contamination is caught.
- Use the production DB driver in integration tests (PostgreSQL via `conftest.py` setup/teardown) — **never** SQLite-as-a-substitute (`rules/ai-agents.md` rule 5).

---

## Stateful Capabilities Need a Second Interaction

A capability that **carries state** — persistent sessions, conversation history, memory, caches, anything that "remembers" or survives a reload/restart — has a bug class the first call can never expose: detached ORM rows, stale or unscoped caches, history-load crashes, session-scoping errors. These fire on the **second** interaction, or after the process restarts — not the first.

So a single happy-path test of a stateful capability is **not coverage of that capability**. For every stateful capability:

- **Multi-interaction test** — drive ≥2 operations in the *same* session/context and assert the later one succeeds AND sees the earlier state (ask → ask-again; create → read → update → read). The bug that shipped past a green Phase-1 gate (history loaded after its DB session closed → `DetachedInstanceError` on the 2nd question) was invisible to every single-turn test; one two-turn test would have caught it.
- **State-survival test** — reload the page / restart the process, then assert prior state is still present and usable.

Derive what to test from the phase's **capabilities**, not its endpoints: if the spec claims "persistent sessions" or "remembers across…", the absence of a multi-interaction + survival test is a coverage hole, regardless of line coverage.

---

## The Pyramid

| Level | Count | Speed | Scope |
|-------|-------|-------|-------|
| Unit | many | ms | one function/class, all deps stubbed |
| Integration | fewer | 100s of ms | real DB and real LLM/API boundary (keys from `.env`) |
| E2E / smoke | fewest | seconds | a real process, golden-path user journey |

Push assertions **down** the pyramid: if a unit test can catch it, don't wait for the smoke test. The golden-path UI smoke test (Phase 2 gate) runs against the **live provider** and asserts **real response content**, not just status codes — a 200 that renders a broken or stub-looking page is a failing test.

---

## Coverage Is a Floor, Not a Goal

- Cover every branch of business logic and every documented error path.
- Don't chase 100% by testing trivial getters or framework glue — that's noise.
- A line covered by a test with no meaningful assertion is **not** covered. Coverage tools count execution, not verification; you count verification.

---

## Before You Claim Done

- Run the **full** suite, not just the test you touched. Show the output.
- "It should pass" is not a passing test (`rules/ai-agents.md` rule 2). Run it or say you couldn't.
- A phase is not complete until its gate suite is green against the production DB driver WITH real LLM/API keys from `.env`, including edge-case and E2E/UI tests.
