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

6. **Golden-path UI smoke test is mandatory before Phase 2 passes.** If the project has any UI or HTTP surface, Phase 2 must include an automated test that walks the full primary user journey via `TestClient` (or equivalent) and asserts **response content**, not just status codes. A build that returns 200 but renders a broken-looking page is a failing build.

7. **Stub / offline providers must be clearly signalled in the UI.** If an LLM provider is stubbed (no key, demo mode), the UI must display a visible banner on every page. Silent stubs that look like real output are a bug — users will report "it didn't work." The provider should auto-select real when an API key is present (`provider=auto` → real when key set, stub otherwise). Never require the user to flip a flag *in addition* to setting the key.

8. **Stub LLM outputs must be distinct per pipeline node and article-shaped.** Pipeline nodes that share a stub provider must inject unambiguous tags (e.g. `<node:plan>`, `<node:draft>`, `<node:title>`) into their prompts, and the stub must branch on those tags — never on prose keywords from the prompt body (keyword matching cross-contaminates: the word "outline" in a draft prompt must not cause the stub to emit outline bullets instead of a draft). Stub "draft" output must contain paragraphs/headings, not just bullets, so offline demos are credible.

9. **Every commit must be pushed immediately.** `git commit` and `git push` are a single atomic action — never one without the other. Use `git commit -m "..." && git push origin <branch>` as a single command. A commit that is not pushed does not exist as far as the project is concerned. This is not optional and is not context-compression-safe — if you remember only this sentence: **commit then push, every time, no exceptions.**

10. **`main` is boilerplate-only. Never commit application code to `main`.** All application code lives on a named feature branch and reaches `main` only via a reviewed pull request. This rule has no exceptions:
    - Before writing any application code, create a feature branch: `git checkout -b feature/<slug>-v0.1`
    - All phase commits go to the feature branch, never to `main`
    - Spec, harness, and boilerplate improvements (no app code) are the only commits that may go directly to `main`
    - When the build is complete, open a PR from the feature branch into `main` — do not merge locally
    - If you find yourself on `main` while writing application code, stop immediately, create the feature branch, and continue there

11. **A PR must exist before the first feature-branch commit, and every push must go to that PR.** After creating the feature branch and pushing the first commit, immediately open a PR: `gh pr create --base main --head feature/<slug>-v0.1`. Every subsequent `git push` automatically updates the same PR — no extra step needed — but the PR must be open. Pushing commits without an open PR is equivalent to committing without pushing: the work is invisible and unreviable. This is not optional and survives context compression.

---

## 1. Session Start Checklist

Complete all steps in order before writing any code:

- [ ] Read `spec/vision.md` — know what you're building
- [ ] Check if the spec is complete (no `<!-- FILL IN -->` markers in product spec files)
  - If incomplete: tell the user to run `/zero-shot-build`; do not write application code
- [ ] If spec is complete: read the full spec manifest in `CLAUDE.md`
- [ ] Run `git status` — working tree must be clean before starting
- [ ] **Create and switch to a feature branch**: `git checkout -b feature/<slug>-v0.1` — **never build on `main`**
- [ ] **Create the project directory** `<agent-slug>/` if it doesn't exist — never write agent code into the boilerplate root
- [ ] Open a session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` — **must exist before Phase 1 starts**
- [ ] Confirm which phase you are implementing (see `harness/phases.md`)

## 2. Session Report (Mandatory)

Every session must have a report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`. The `reports/` directory is gitignored — these logs are local to the machine running the build.

### Required structure

```markdown
# Session — YYYY-MM-DD HH:MM

**Branch:** feature/<slug>-v0.1
**Phase:** <current phase number and name>
**Goal:** <one sentence — what this session is trying to accomplish>
**Started:** HH:MM

---

## Steps

<!-- Log entries in real time. Format: HH:MM — [agent or action] — [what happened / outcome] -->

HH:MM — [session start] — read spec, confirmed phase N in scope, working tree clean
HH:MM — [code-generator] — implemented X, Y, Z; gate ran, PASS
HH:MM — [code-reviewer] — APPROVED / returned 2 blockers: ...
HH:MM — [qa-auditor] — VERIFIED / BLOCKED: <specific failures>
HH:MM — [deployer] — committed + pushed phase-N (abc1234)

---

## Decisions & Assumptions

<!-- Record any non-obvious choice made during this session and why. -->

- <decision>: <rationale>

---

## Blockers & Open Questions

<!-- Anything that stopped progress or needs user input. -->

- [ ] <blocker or question>

---

## Latency Log

| Stage | Agent | Start | End | Duration |
|-------|-------|-------|-----|----------|
| Spec draft | spec-writer | HH:MM | HH:MM | Xm |
| Spec review | spec-reviewer | HH:MM | HH:MM | Xm |
| Tech design | tech-architect | HH:MM | HH:MM | Xm |
| Phase 1 code | code-generator | HH:MM | HH:MM | Xm |
| Phase 1 review | code-reviewer | HH:MM | HH:MM | Xm |
| Phase 1 gate | qa-auditor | HH:MM | HH:MM | Xm |
| Phase 1 deploy | deployer | HH:MM | HH:MM | Xm |

---

## End State

**Finished:** HH:MM
**Phase completed:** <N>
**Tests:** PASS / FAIL
**Working tree:** clean / dirty (explain)
**Next session starts at:** Phase <N+1> — <brief description>

---

## Harness Notes

<!-- Anything this session revealed about the harness itself — confusing rules, missing guidance, slow stages, false-positive gates. These feed harness improvements. -->

- <observation>
```

### Rules for filling in the report

- **Log in real time** — do not reconstruct at the end. Each step entry as it happens.
- **Timestamp every action** — start + end time per agent stage. Latency data is how we improve the harness.
- **Decisions are permanent** — if you chose something non-obvious (a library, a schema shape, a stub strategy), record it. Future sessions need to know why.
- **Blockers are actionable** — if you're blocked, write the exact question or failure. Not "blocked on DB" but "blocked: `psycopg2` not in PATH, suspect missing C library — need user to run `brew install libpq`."
- **Harness Notes are gold** — any observation about where the harness slowed you down or gave wrong guidance is a first-class output, not a throwaway comment.

## 3. Gate Law

The goal is: **one prompt → working skeleton in ~10 minutes.** All decisions are captured upfront and approved once. There is exactly one user approval gate before code is written.

```
INTAKE (4 questions: scope, stack, trigger, constraints)
        ↓
DRAFT (spec + tech design + plan produced together)
        ↓
ONE APPROVAL (user sees everything at once — one response to proceed)
        ↓
BUILD (Phase 1 → Phase 2, each gated by passing tests)
```

**Rules that never change:**
- Stack decisions (database, language, hosting) belong to the user — captured at intake, never chosen autonomously
- No code is written before the single approval gate is cleared
- Each build phase must pass its gate test before the next phase starts
- spec-reviewer reviews the spec and code-reviewer reviews the code; tech-architect self-reviews its design; qa-auditor gates each phase. None of these add a user approval round for v0.1 — there is exactly one approval gate (after intake)

**After v0.1 is running**, subsequent phases follow the standard gate:
```
[Phase implemented] → [gate test passes] → [committed] → [next phase]
```

---

## 4. Spec-First Rule

**No code change without a spec backing it.**

If you are asked to implement something not in the spec:
1. Stop
2. Tell the user what spec gap you found
3. Propose adding it to the spec first
4. Wait for approval before writing code

See `harness/spec-driven.md` for full details.

## 5. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.**

Each phase ends when:
- All code for that phase is written and committed
- All tests for that phase pass
- The qa-auditor sub-agent has returned VERIFIED (or you have run the gate checklist manually)

See `harness/phases.md` for the phase definitions and gates.

## 6. Git Discipline

- Commit every logical unit of work — never let the working tree stay dirty for more than one logical change
- **Push immediately after every commit** — treat `git commit -m "..." && git push origin <branch>` as a single indivisible command. Never leave a commit unpushed.
- Commit message format: `phase-N: [what you did]` (e.g., `phase-1: add domain models`)
- Never commit secrets (API keys, passwords, tokens)
- Never force-push without user confirmation
- **Never `git add -A` / `git add .`** — always stage specific files or directories. `-A` sweeps in untracked leftovers from prior build attempts (stray packages, abandoned experiments) and poisons the commit. If a phase needs many files, list them explicitly or stage directories one at a time.

**Before every reply to the user:**
1. Run `git status`
2. If dirty: commit the changes with `git commit -m "..." && git push origin <branch>`
3. Confirm the working tree is clean **and** the branch is pushed before replying

## 7. Test Before Claiming Done

A phase is not done until tests pass. "It looks right" is not a test.

- Write tests for each capability as you implement it
- Run the full test suite before marking a phase complete
- If tests fail, fix them before moving on

## 8. Error Resilience

Every external call (API, database, LLM) must have:
- Error handling that doesn't crash the agent
- Logged failures (to file or stdout at minimum)
- Graceful degradation (the agent continues if a non-critical step fails)

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
