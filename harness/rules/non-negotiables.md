# Non-Negotiables

These rules are never optional and must survive context compression. If you can remember
only a few rules, remember these.

1. **Humans own the goal.** No code is written until the spec is complete enough to act
   and the supervisor has reviewed it (with researcher, engineer feasibility, reviewer
   testability). Elicit as much as needed — the loop catches the rest.

2. **Spec before code.** No change to `src/` without a backing change in `spec/`. If
   asked to build something not in the spec: stop, name the gap, spec it, get sign-off,
   then build. (See `spec-driven.md`.)

3. **Outcome is evidence.** Never claim a test passed without running it. "It should
   work" is not a result. Show the output, or say you couldn't run it.

4. **Docs must be true.** Every command in the README and docs must work exactly as
   written, from the directory stated. Test them before marking work done. A README that
   lies is worse than no README.

5. **Git discipline.** Stage specific files only — never `git add -A`. Commit and push
   are one indivisible action; a commit that is not pushed does not exist. All code
   lives on a feature branch and reaches `main` only via a reviewed PR; open the PR
   before the first feature-branch commit. (See `git-and-delivery.md`.)

6. **One phase at a time.** Never start phase N+1 while phase N is failing. Each phase
   runs end-to-end and passes its gate first. (See `../process/lifecycle.md`.)

7. **The loop must close before you stop.** Before ending any unit of work: spec ↔ src ↔
   logs reconcile, tests pass, the tree is clean, the branch is pushed, and the session
   report in `logs/sessions/` is up to date.
