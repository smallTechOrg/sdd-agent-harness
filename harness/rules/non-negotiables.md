# Non-Negotiables

These rules are never optional and must survive context compression. If you can remember
only a few rules, remember these.

**Cite on override.** These rules are numbered so they can be cited. Overriding any one
requires naming its number and logging a one-line justification in the session report — an
override is a deliberate, recorded act, never a silent one.

1. **Humans own the goal.** No code is written until the spec is complete enough to act
   and the supervisor has reviewed it (with researcher, executor feasibility, reviewer
   testability). Elicit as much as needed — the loop catches the rest.

2. **Spec before code.** No change to `src/` without a backing change in `spec/`. If
   asked to build something not in the spec: stop, name the gap, spec it, get sign-off,
   then build. (See `spec-driven.md`.)

3. **Outcome is evidence.** Never claim a test passed without running it. "It should
   work" is not a result. Show the output, or say you couldn't run it. Tests run against the
   **production data driver** (never a SQLite stand-in), and a green stub run is paired with
   golden-case **evals** — coverage is not correctness.

4. **Docs must be true.** Every command in the README and docs must work exactly as
   written, from the directory stated. Test them before marking work done. A README that
   lies is worse than no README.

5. **Git discipline.** Stage specific files only — never `git add -A`. Commit and push
   are one indivisible action; a commit that is not pushed does not exist. All code
   lives on a feature branch and reaches `main` only via a reviewed PR; open the PR
   before the first feature-branch commit. (See `git-and-delivery.md`.)

6. **Steps gate green; the iteration gates hard.** The whole requirement ships in **one
   iteration**, built as parallel **steps** (see `workflows/build.md` → Vocabulary).
   - A **step** is done when its fast gate (<30s) is green and the analyser sees no drift on
     handoff. Never wire a dependent step on top of a red step.
   - The **iteration** is done only when the full reviewer checklist passes, evals are green,
     the tree is clean and pushed, and the session report is current. This heavy gate runs
     **once**, on the converged whole — not per step.

7. **The loop must close before you stop.** Before ending any unit of work: spec ↔ src ↔
   logs reconcile (the drift check is clean), tests and evals pass, the tree is clean, the
   branch is pushed, and the session report in `logs/sessions/` is up to date.

8. **Done means the user says done.** Tests passing and reviewer sign-off are necessary
   but not sufficient. The **iteration** is complete only when the user has explicitly
   accepted the delivered requirement — the one user-acceptance boundary. Never self-declare
   done.

9. **Never act irreversibly without confirmation.** Deploy, delete, send email, write to
   a production DB, force-push — any action that cannot be undone requires explicit
   approval from the user via the supervisor before proceeding. Timeout is a rejection.

10. **Blockers route to the fix workflow.** If the executor cannot resolve a blocker in
    three attempts, stop immediately, do not hack around it, and route to the fix
    workflow. The analyser diagnoses; the planner re-scopes.

11. **Collect API keys at intake.** Ask for all required API keys before the build begins.
    Never ask mid-build. If a key is missing and was not collected at intake, pause and
    surface to the user — do not continue in a degraded state without telling them.

12. **Timestamp every action, and account for the wall-clock.** Each stage **and each step**
    records a wall-clock **start and end time** in its session-report section (and gate commands
    log their own timestamps), plus a one-word **dominant cost** (model-latency | tooling/network |
    rework/retry | waiting-on-user | waiting-on-background). Every run fills the **Latency ledger**
    (one row per step, in execution order) so the critical path and dominant cost are *computable*,
    not guessed — this is the data we mine to make runs faster. A stage/step with no timing, or a
    run with an empty ledger, is **incomplete** and the analyser flags it. Use the host clock
    (`date '+%Y-%m-%d %H:%M:%S'`); never invent a time.
