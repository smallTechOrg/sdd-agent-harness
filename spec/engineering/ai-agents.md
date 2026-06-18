# AI Agent Rules

**These rules apply to every AI coding session in this repo — Claude Code, GitHub Copilot, Cursor, or any other AI assistant.**

Read this file completely before doing anything else.

---

## ⚠ Non-Negotiable Rules

These rules are never optional, never skipped, and must survive context compression. If your context window is compressed and you can only remember a few rules, these are the ones.

1. **README must always be accurate.** Every command in the README must work exactly as written, from the directory stated. Before ending any session or marking any phase complete: run the README commands yourself — if any fail, fix the README first. A README that lies is worse than no README.

2. **Never claim a test passed if you didn't run it.** "It should work" is not a passing test. Run `pytest` (or equivalent). Show the output. If you can't run it, say so — do not fabricate results.

3. **All commands in docs use the package manager prefix.** For Python + uv projects: every `alembic`, `pytest`, `python` command in the README and docs must be prefixed with `uv run`. Bare commands (e.g. `alembic upgrade head`) fail unless the venv is manually activated — which users won't do.

4. **Working directory must be explicit.** Any README or doc section with shell commands must state the exact working directory at the top of the code block. "Run from project root" is not enough — give the exact relative path from the repo root.

5. **No SQLite substitute for PostgreSQL tests.** If the production database is PostgreSQL, tests run against PostgreSQL. Tests that only pass on SQLite do not count as passing.

6. **Golden-path UI smoke test is mandatory before Phase 2 passes.** If the project has any UI or HTTP surface, Phase 2 must include an automated test that walks the full primary user journey via `TestClient` (or equivalent) and asserts **response content**, not just status codes. See `spec/engineering/workflows/golden-path-smoke-test.md`. A build that returns 200 but renders a broken-looking page is a failing build.

7. **Stub / offline providers must be clearly signalled in the UI.** If an LLM provider is stubbed (no key, demo mode), the UI must display a visible banner on every page. Silent stubs that look like real output are a bug — users will report "it didn't work." The provider should auto-select real when an API key is present (`provider=auto` → real when key set, stub otherwise). Never require the user to flip a flag *in addition* to setting the key.

8. **Stub LLM outputs must be distinct per pipeline node and article-shaped.** Pipeline nodes that share a stub provider must inject unambiguous tags (e.g. `<node:plan>`, `<node:draft>`, `<node:title>`) into their prompts, and the stub must branch on those tags — never on prose keywords from the prompt body (keyword matching cross-contaminates: the word "outline" in a draft prompt must not cause the stub to emit outline bullets instead of a draft). Stub "draft" output must contain paragraphs/headings, not just bullets, so offline demos are credible.

9. **Agents that act on the outside world must use a ReAct loop — never a "sample and guess" pipeline.** If the agent answers questions using tools, data (CSV, databases, APIs, files), or search, it must generate executable actions, run them against the **full** data, and feed results back to the LLM iteratively (reason/plan → act → observe, looping) until the LLM signals a final answer. A single-shot pipeline that passes a sample to the LLM produces wrong results at scale and must be redesigned before Phase 2 is marked complete. Spec the loop in `07-agent-graph.md` before writing any code; see Section 10 for the full pattern.

10. **Every commit must be pushed immediately.** `git commit` and `git push` are a single atomic action — never one without the other. Use `git commit -m "..." && git push origin <branch>` as a single command. A commit that is not pushed does not exist as far as the project is concerned. This is not optional and is not context-compression-safe — if you remember only this sentence: **commit then push, every time, no exceptions.**

11. **`main` is boilerplate-only. Never commit application code to `main`.** All application code lives on a named feature branch and reaches `main` only via a reviewed pull request. This rule has no exceptions:
    - Before writing any application code, create a feature branch: `git checkout -b feature/<slug>-v0.1`
    - All phase commits go to the feature branch, never to `main`
    - Spec/engineering/boilerplate improvements (no app code) are the only commits that may go directly to `main`
    - When the build is complete, open a PR from the feature branch into `main` — do not merge locally
    - If you find yourself on `main` while writing application code, stop immediately, create the feature branch, and continue there

12. **A PR must exist before the first feature-branch commit, and every push must go to that PR.** After creating the feature branch and pushing the first commit, immediately open a PR: `gh pr create --base main --head feature/<slug>-v0.1`. Every subsequent `git push` automatically updates the same PR — no extra step needed — but the PR must be open. Pushing commits without an open PR is equivalent to committing without pushing: the work is invisible and unreviable. This is not optional and survives context compression.

---

## 1. Session Start Checklist

Complete all steps in order before writing any code:

- [ ] Read `spec/product/01-vision.md` — know what you're building
- [ ] Check if the spec is complete (no `<!-- FILL IN -->` markers in product spec files)
  - If incomplete: surface the agent-builder to the user; do not write application code
- [ ] If spec is complete: read the full spec manifest in `CLAUDE.md`
- [ ] Run `git status` — working tree must be clean before starting
- [ ] **Create and switch to a feature branch**: `git checkout -b feature/<slug>-v0.1` — **never build on `main`**
- [ ] **Create the project directory** `<agent-slug>/` if it doesn't exist — never write agent code into the boilerplate root
- [ ] Open a session report: `<agent-slug>/reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` — **must exist before Phase 1 starts**
  - Use the template in `spec/engineering/workflows/session-report.md`
- [ ] Confirm which phase you are implementing (see `spec/engineering/phases.md`)

## 2. Session Report (Mandatory)

Every session must have a report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`.

Minimum required sections:
- **Goal:** What this session is trying to accomplish
- **Phase:** Which implementation phase
- **Steps completed:** Logged as you work (not reconstructed at the end)
- **Prompt log:** Every user message and a one-line summary of your action
- **Next steps:** What remains

Update the report in real time. Do not reconstruct it from memory at the end.

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
- Reviewers (spec-reviewer, plan-reviewer) run as background validation and surface blockers, but do not add approval rounds for v0.1

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

See `spec/engineering/spec-driven.md` for full details.

## 5. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.**

Each phase ends when:
- All code for that phase is written and committed
- All tests for that phase pass
- The qa-auditor sub-agent has signed off (or you have run the QA checklist manually)

See `spec/engineering/phases.md` for the phase definitions and gates.

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

## 10. Agent Loop Design Patterns

### The ReAct loop

Any agent that acts on the outside world to answer a question — tool use, data queries, web search, file/API access — must run a **ReAct** ("Reason + Act") loop, not a single-shot pipeline. Each iteration runs the same cycle and repeats until the agent signals it is done:

**reason/plan** (LLM picks the next action, or signals done) → **act** (execute it) → **observe** (feed the result back into the next reason step).

Reasoning and acting interleave every iteration — that is what makes it ReAct rather than planning everything up front. A single-shot pipeline ("gather context, pass to the LLM, return its answer") cannot verify its inputs or self-correct, and breaks down once the real environment differs from the sampled context.

```
START → setup → plan_action ──(action)──► execute_action ──┐
                  ▲   │                                     │
                  │   ├─(FINAL ANSWER)─► finalize → END     │
                  │   └─(fatal error)─► handle_error → END  │
                  └──────────(observe: result loops back)───┘
                                                            │
   (max iterations OR repeated errors) ─► force_finalize ─► END
```

- **setup** — prepare what the agent acts on (load data, open a connection, build an index)
- **plan_action** = reason/plan · **execute_action** = act · result appended to state and looped back = observe

### Mandatory mechanics

- **Termination signal.** The LLM ends the loop with a fixed prefix, e.g. `FINAL ANSWER: <text>`. `plan_action` checks for it (case-insensitive): if present, strip it and route to `finalize`; otherwise treat the response as the next action. Without this the loop never terminates on its own.
- **Max-iterations guard.** Configurable ceiling (`max_agent_iterations`, default 10). On reaching it — or after repeated consecutive errors — route to **`force_finalize`**, never loop unboundedly.
- **Best-effort finalization (`force_finalize`).** Running out of iterations is not a crash: synthesise the best answer from `action_history` and note what's missing — never a bare "I couldn't do it." Reserve `handle_error` for fatal failures (data missing, LLM/network down).
- **Self-correction.** On a recoverable action error (bad query, API 4xx, missing file), append the action + error to history and route back to `plan_action` so the LLM sees it inline and retries. Hard-fail (→ `handle_error`) only on a structurally invalid action or an LLM-call failure.
- **Action-safety boundary.** Treat model-generated actions as untrusted: permit only an explicit operation set (read-only `SELECT`, a named tool allowlist), validate each action before running it, and never `exec`/`eval` raw output unsandboxed.
- **Operator observability.** Every LLM call returns structured usage (input/output tokens, estimated cost) accumulated in state and persisted on the run; every node emits a structured (JSON) log bound to `run_id`. Token/cost per run must never be invisible.
- **User transparency.** Observability is not only logs. The agent must show the user *what it is doing as it happens* — each step's action, its result, then the final answer — streamed or rendered from `action_history`. The run is a glass box, never a spinner hiding a black box.

### State

`AgentState` carries the context the LLM needs on every `plan_action` call:

```python
action_history: list[dict]  # [{"action": str, "result": str, "is_error": bool}]
iteration_count: int
llm_response: str           # raw last LLM output — router inspects it for FINAL ANSWER
tokens_input: int           # accumulated usage — persisted on the run record
tokens_output: int
estimated_cost_usd: float | None
```

Persist `action_history` — it is both the live user-facing trace and the audit log — along with the usage fields. Resources that can't be serialized into state (DB connection, vector index, file handle) live in a module-level store keyed by `run_id`, released in **every** terminal node (`finalize`, `force_finalize`, `handle_error`) — prefer a `finally` block so no path can leak the resource.

### Spec it before coding

`07-agent-graph.md` must answer, before any node code is written: (1) what action the LLM generates (query, HTTP request, file path, tool call…); (2) the exact FINAL ANSWER string; (3) the recoverable-vs-fatal error boundary; (4) the max-iterations default; (5) what `setup` prepares and how it's cleaned up; (6) what fields `AgentState` carries for history, iteration count, and usage — and how the trace is surfaced to the user live; (7) the **action-safety boundary** — which operations the executor permits, how each action is validated before running, and what sandbox it runs in; (8) what `force_finalize` synthesises when iterations are exhausted. If any are missing, raise a blocker before Phase 2.

---

## 11. When Stuck

If requirements are unclear:
1. Stop
2. List your specific questions in the session report
3. Ask the user — do not guess

If the spec is ambiguous:
1. State the ambiguity
2. Propose an interpretation
3. Wait for confirmation before implementing

## 12. Closing a Session

Before ending a session:
- [ ] Working tree is clean (all changes committed and pushed)
- [ ] Session report is complete and up to date
- [ ] Tests pass
- [ ] `README.md` updated if project layout, setup steps, or commands changed
- [ ] Note which phase you're on and what comes next in the session report
