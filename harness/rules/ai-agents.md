# AI Agent Rules

**These rules apply to every Claude Code session in this repo.**

Read this file completely before doing anything else.

---

## ⚠ Non-Negotiable Rules

These rules are never optional, never skipped, and must survive context compression. If your context window is compressed and you can only remember a few rules, these are the ones.

1. **README must always be accurate.** Every command in the README must work exactly as written, from the directory stated. Before ending any session or marking any phase complete: run the README commands yourself — if any fail, fix the README first. A README that lies is worse than no README.

2. **Never claim a test passed if you didn't run it.** "It should work" is not a passing test. Run `pytest` (or equivalent). Show the output. If you can't run it, say so — do not fabricate results.

3. **All commands in docs use the package manager prefix.** For Python + uv projects: every `alembic`, `pytest`, `python` command in the README and docs must be prefixed with `uv run`. Bare commands (e.g. `alembic upgrade head`) fail unless the venv is manually activated — which users won't do.

4. **Working directory must be explicit.** Any README or doc section with shell commands must state the exact working directory at the top of the code block. "Run from project root" is not enough — give the exact relative path from the repo root.

5. **No SQLite substitute for PostgreSQL tests.** If the production database is PostgreSQL, tests run against PostgreSQL. Tests that only pass on SQLite do not count as passing.

6. **Golden-path UI smoke test is mandatory before Phase 2 passes.** If the project has any UI or HTTP surface, Phase 2 must include an automated test that walks the full primary user journey end-to-end against the **real LLM/API** (keys from `.env`) via `TestClient` (or equivalent) and asserts **response content**, not just status codes. A build that returns 200 but renders a broken-looking page is a failing build. Edge-case and end-to-end coverage of the journey are required, not optional.

7. **Tests and evals run against the real LLM/API using keys loaded from `.env`.** There is no offline-passing requirement; real-key execution is the default and required path for every gate, against the production DB driver (never SQLite if production is PostgreSQL). A stub provider MAY exist as an optional local fallback when a key is genuinely absent, but it is never the gate. The quality bar is perfect, zero errors — edge-case, end-to-end, and UI tests are required, not optional.

8. **Every commit must be pushed immediately.** `git commit -m "..." && git push origin <branch>` is one indivisible action — a commit that isn't pushed doesn't exist. See `harness/rules/git.md`.

9. **`main` is boilerplate-only. Never commit application code to `main`.** App code lives on a feature branch and reaches `main` only via a reviewed PR. See `harness/rules/git.md`.

10. **A PR must exist before the first feature-branch commit.** Open it right after the first push (`gh pr create --base main --head feature/<slug>-v0.1`); every later push updates it. See `harness/rules/git.md`.

---

### Optional stub fallback (non-normative)

The real provider is the default and what every gate tests. A stub provider MAY exist purely as a local fallback for when a key is genuinely absent:

- It should auto-select real when a key is present (`provider=auto` → real when key set), never requiring the user to flip a flag *in addition* to setting the key.
- If an active stub is ever used, signal it visibly in the UI so demo output is never mistaken for real output.
- If implemented, its per-node outputs should be distinct (branch on injected node tags, never on prose keywords) and shaped like real output, so the fallback is not misleading.

None of this is gated — the Phase 2 gate runs against real keys.

---

## 1. Session Start Checklist

Complete all steps in order before writing any code:

- [ ] Read `spec/roadmap.md` — know what you're building
- [ ] Check if the spec is complete (no `<!-- FILL IN -->` markers in product spec files)
  - If incomplete: tell the user to run `/zero-shot-build`; do not write application code
- [ ] If spec is complete: read the full spec manifest in `CLAUDE.md`
- [ ] Run `git status` — working tree must be clean before starting
- [ ] **Create and switch to a feature branch**: `git checkout -b feature/<slug>-v0.1` — **never build on `main`**
- [ ] **Create the project directory** `<agent-slug>/` if it doesn't exist — never write agent code into the boilerplate root
- [ ] Confirm `.env` exists and contains the required API keys/secrets (requested at intake) — tests and the build run against the real LLM/API using these keys
- [ ] Open a session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` — **must exist before Phase 1 starts**
- [ ] Confirm which phase you are implementing (see `harness/patterns/phases.md`)

## 2. Session Report (Mandatory)

Every session must have a report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`. The `reports/` directory is gitignored — these logs are local to the machine running the build.

### Required structure

Top-matter (`Branch`, `Phase`, `Goal`, `Started`), then these sections:

- **Steps** — real-time log, one line per action: `HH:MM — [agent or action] — [what happened / outcome]`.
- **Decisions & Assumptions** — `<decision>: <rationale>` for any non-obvious choice.
- **Blockers & Open Questions** — the exact failure or question.
- **Latency Log** — a table with `Stage | Agent | Start | End | Duration`, one row per agent stage.
- **End State** — `Finished`, `Phase completed`, `Tests` (PASS/FAIL), `Working tree`, `Next session starts at`.
- **Harness Notes** — anything this session revealed about the harness itself (confusing rules, slow stages, false-positive gates).

### Rules for filling in the report

- **Log in real time** — do not reconstruct at the end. Each step entry as it happens.
- **Timestamp every action** — start + end time per agent stage. Latency data is how we improve the harness.
- **Decisions are permanent** — record any non-obvious choice (a library, a schema shape, a provider choice) and why.
- **Blockers are actionable** — write the exact question or failure, not "blocked on DB" but "blocked: `psycopg2` not in PATH, suspect missing C library — need user to run `brew install libpq`."
- **Harness Notes are gold** — observations about where the harness slowed you down are a first-class output.

## 3. Build Flow

The goal is: **one prompt → a perfectly-working, thoroughly-tested agent in ~20-30 minutes, with zero user interaction after intake.** There is no build/approval gate. Intake is the only interactive step: it captures scope, stack, trigger, and constraints, may ask additional clarifying questions up front, and asks the user to fill `.env` with the required API keys/secrets. Once intake completes, agent-builder runs design → scaffold → build → ship autonomously, with zero further user interaction.

```
INTAKE (capture scope, stack, trigger, constraints; ask additional clarifying
        questions up front if anything is ambiguous; request the user fill .env
        with the required API keys/secrets)
        ↓
BUILD (spec + tech design + plan, then Phase 1 → Phase 2, each gated by passing
       real-key tests) — runs autonomously, no approval gate
```

**Rules that never change:**
- Stack decisions (database, language, hosting) belong to the user — captured at intake, never chosen autonomously.
- Filling `.env` is the only manual user step, requested at intake; after intake there is no further user interaction.
- Each build phase must pass its gate against the real LLM/API before the next phase starts.
- spec-writer and tech-architect each self-review their output, and qa-auditor independently reviews the code and gates each phase — none of these add a user approval round.

```
[Phase implemented] → [real-key gate passes] → [committed] → [next phase]
```

---

## 4. Spec-First Rule

**No code change without a spec backing it.**

If you are asked to implement something not in the spec:
1. Stop
2. Tell the user what spec gap you found
3. Propose adding it to the spec first
4. Wait for approval before writing code

See `harness/patterns/spec-driven.md` for full details.

## 5. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.**

Each phase ends when:
- All code for that phase is written and committed
- All tests for that phase pass
- The qa-auditor sub-agent has returned VERIFIED (or you have run the gate checklist manually)

See `harness/patterns/phases.md` for the phase definitions and gates.

## 6. Git Discipline

See `harness/rules/git.md` for the full rules. Summary:

- Commit every logical unit of work — never let the working tree stay dirty for more than one logical change
- **Push immediately after every commit** — `git commit -m "..." && git push origin <branch>` is one indivisible action
- Commit message format: `phase-N: [what you did]`
- Never commit secrets; never force-push without user confirmation
- **Never `git add -A` / `git add .`** — stage specific files only

**Before every reply to the user:**
1. Run `git status`
2. If dirty: commit and push
3. Confirm the working tree is clean **and** the branch is pushed before replying

## 7. Test Before Claiming Done

A phase is not done until all tests pass against the real LLM/API. "It looks right" is not a test. The quality bar is perfect, zero errors — not fast and minimal.

- Write tests for each capability as you implement it, including edge cases
- Cover end-to-end and UI journeys (real keys) for any UI/HTTP surface
- Run the full suite against keys from `.env` before marking a phase complete
- If tests fail, fix them before moving on

## 8. Error Resilience

Every external call (API, database, LLM) must have:
- Error handling that doesn't crash the agent
- Logged failures (to file or stdout at minimum)
- Graceful degradation (the agent continues if a non-critical step fails)

Surface a clear, actionable error when an API key is missing or invalid (point the user at `.env`) — never silently fall back in a way that hides a real failure during tests.

## 9. No Gold-Plating

Build what the spec says, nothing more.

- No extra features "while you're in there"
- No refactoring outside the current phase scope
- No premature abstractions
- If you spot a future improvement, add it to `reports/sessions/[current].md` under "Future improvements" and keep moving

## 10. When Stuck

If requirements are unclear:
1. Stop
2. List your specific questions in the session report
3. Ask the user — do not guess

If the spec is ambiguous:
1. State the ambiguity
2. Propose an interpretation
3. Wait for confirmation before implementing

## 11. Closing a Session

Before ending a session:
- [ ] Working tree is clean (all changes committed and pushed)
- [ ] Session report is complete and up to date
- [ ] Tests pass
- [ ] `README.md` updated if project layout, setup steps, or commands changed
- [ ] Note which phase you're on and what comes next in the session report
