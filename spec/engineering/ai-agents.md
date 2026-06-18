# AI Agent Rules

**Applies to every AI coding session in this repo** — Claude Code, Copilot, Cursor, any assistant.
Read this file completely before doing anything else. Each rule lives here once; deeper detail lives in
the linked canonical file.

---

## ⚠ Non-Negotiables (must survive context compression)

If your context is compressed and you can remember only a few rules, these are the ones.

1. **The README must always be accurate.** Every command must work exactly as written, from the stated
   directory. Run them yourself before ending a session or marking a phase complete; if any fails, fix
   the README first. → [`project-layout.md`](project-layout.md) § README Requirements.
2. **Never claim a test passed without running it.** "It should work" is not a pass. Run it, show the
   output. If you can't run it, say so — never fabricate results.
3. **Commit then push, every time.** `git commit -m "…" && git push origin <branch>` is one indivisible
   action. An unpushed commit does not exist. → § 6.
4. **`main` is boilerplate-only.** Application code lives on a `feature/<slug>-<date>` branch and reaches
   `main` only via a reviewed PR, and a PR must exist before the first feature-branch commit. → § 6.
5. **Agents that act on the outside world use a ReAct loop**, never a sample-and-guess pipeline. Spec
   it before coding. → [`patterns/react-agent.md`](patterns/react-agent.md).

---

## 1. Session Start

Complete in order before writing any code:

- [ ] Read `spec/product/01-vision.md` — know what you're building.
- [ ] Check the spec is complete (no `<!-- FILL IN -->` in `spec/product/`). If incomplete, surface the
      agent-builder and **do not write application code**.
- [ ] If complete, read the full spec manifest in `CLAUDE.md`.
- [ ] `git status` — the working tree must be clean.
- [ ] Create and switch to a feature branch: `git checkout -b feature/<slug>-<date>`. **Never build on `main`.**
- [ ] Open a session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` — **must exist before
      Phase 1.** → § 2.
- [ ] Confirm which phase you're implementing (`phases.md`).

## 2. Session Report

Every session has a report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`, using the template in
[`workflows/session-report.md`](workflows/session-report.md). It is a **handoff document**: log **every
activity** — not just builds, but spec edits, investigations, decisions, and dead ends — in real time, so
the user can switch chats or coding agents and resume seamlessly. Capture Goal, Phase, steps, a prompt
log, and next steps as you go — never reconstruct it at the end. `reports/` is gitignored (the template
under `workflows/` stays tracked); a missing session report is a build failure.

## 3. The One-Approval Gate Law

Goal: **one prompt → working agent fast.** Decisions are captured upfront and approved once. Phase 1
delivers the raised agentic baseline running with **real** integrations (real LLM + MCP tools + memory +
evals), not a bare loop — see § 10.

```
INTAKE (scope · stack · provider · trigger · constraints)  →  DRAFT (spec + tech design + plan together)
   →  ONE APPROVAL (user sees everything, one response)  →  BUILD (Phase 1 = real baseline, then gated phases)
```

- Stack decisions (database, language, hosting, **LLM provider**) belong to the user — captured at
  intake, never chosen autonomously.
- No code before the single approval gate clears.
- Each build phase passes its gate test before the next starts.
- Reviewers (spec-reviewer, plan-reviewer) run as background validation and surface blockers; they do
  not add approval rounds for the first release.

After Phase 1 is running, every later phase follows: implemented → gate test passes → committed → next.

## 4. Spec-First

**No code change without a spec backing it.** If asked to implement something not in the spec: stop,
name the gap, propose adding it to the spec, wait for approval. → [`spec-driven.md`](spec-driven.md).

## 5. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.** A phase ends when its code is
committed and pushed, its tests pass, and the qa-auditor (or the manual QA checklist) has signed off.
→ [`phases.md`](phases.md).

## 6. Git (canonical home)

- Commit every logical unit of work — never leave the tree dirty across more than one logical change.
- **Push immediately after every commit** (Non-Negotiable 3). Never leave a commit unpushed.
- **`main` is boilerplate-only.** All application code lives on `feature/<slug>-<date>` and reaches `main`
  only via PR. Spec/engineering/boilerplate-only changes may commit directly to `main`. If you find
  yourself on `main` writing application code, stop and create the branch first.
- **A PR must exist before the first feature-branch commit** (`gh pr create --base main --head
  feature/<slug>-<date>`). Every later push updates that same PR automatically.
- Commit message format: `phase-N: [what you did]`.
- **Never `git add -A` / `git add .`** — stage specific files or directories; `-A` sweeps in untracked
  leftovers from prior attempts and poisons the commit.
- Never commit secrets (→ [`secret-hygiene.md`](secret-hygiene.md)); never force-push without user
  confirmation.
- **Before every reply:** `git status`; if dirty, commit and push; confirm clean + pushed before replying.

## 7. Test Before Claiming Done

A phase is not done until tests pass; "it looks right" is not a test. Write tests per capability as you
implement, and run the full suite before marking a phase complete.

**Test across every layer**, not just units:

- **Unit** — domain logic, parsing, pure functions.
- **Integration** — the agent loop + DB end-to-end against the **real** model (key from a CI secret),
  with **loose assertions** (structure + non-empty) to tolerate LLM output variance.
- **Golden-path** — the full primary user journey through the HTTP/UI layer, asserting rendered
  **content**, not just status codes. → [`workflows/golden-path-smoke-test.md`](workflows/golden-path-smoke-test.md).
- **Frontend / browser** — any client-rendered content (charts, SPA, htmx, streamed tokens) tested in a
  real browser (Playwright) asserting the post-JavaScript DOM. A `TestClient` HTML check cannot see what
  the browser paints.
- **End-to-end** — at least one test drives the whole stack as a user does (browser → API → agent → DB →
  back), nothing mocked — the model is real.
- **Evals** — a small fixed set of representative inputs with rubric/property checks to catch regressions
  in the agent's *answers*. A run that returns 200 with a wrong analysis passes every layer above.

Tests run against the real model with loose asserts, and use the same DB driver as production. →
[`tech-stack.md`](tech-stack.md) § Database & Tests, [`patterns/llm-providers.md`](patterns/llm-providers.md).

## 8. Error Resilience

Every external call (API, DB, LLM) needs error handling that doesn't crash the agent, logged failures
(file or stdout minimum), and graceful degradation — the agent continues when a non-critical step fails.

## 9. No Gold-Plating

Build what the spec says, nothing more. No extra features "while you're in there", no refactoring
outside the current phase, no premature abstractions. Note future improvements in the session report and
keep moving.

## 10. Agentic Architecture

If the agent acts on the outside world (tools, data, search), it must run a ReAct loop with all the
mandatory mechanics — termination signal, max-iterations guard, `force_finalize`, self-correction, the
action-safety boundary, usage accounting, and a live user-facing trace. Defined once in
[`patterns/react-agent.md`](patterns/react-agent.md).

Build to the **agentic baseline** in [`agentic-architecture.md`](agentic-architecture.md): the default
agent ships memory + MCP tools + evals + OTel tracing, all **real in Phase 1**. Retrieval, long-term
memory, multi-agent, HITL, and durability earn their place in later phases. Before Phase 1, record in
`02-architecture.md` which stack layers apply and why; each layer is defined once in its pattern doc
under [`patterns/`](patterns/) — never restate, link.

## 11. When Stuck

If requirements are unclear or the spec is ambiguous: stop, write the specific questions in the session
report, propose an interpretation, and ask the user — do not guess.

## 12. Closing a Session

- [ ] Working tree clean (all changes committed and pushed).
- [ ] Session report complete and current.
- [ ] Tests pass.
- [ ] README updated if layout, setup, or commands changed.
- [ ] Current phase and next steps noted in the session report.
