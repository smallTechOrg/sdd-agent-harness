# Observability

Patterns for making agent behavior visible and keeping the awareness loop honest.

---

## Log directory structure

```
logs/
  sessions/    build-time journals — one per working session (committed)
  runtime/     the built system's structured logs and traces (git-ignored for live data)
  analysis/    the analyser's findings and reconciliation reports (committed)
```

- `sessions/` files are named `YYYY-MM-DD-HHMMSS-<branch>.md` and must exist before
  Phase 1 starts.
- `runtime/` live data is never committed; only fixtures/examples are.
- `analysis/` is the analyser's written output — findings, drift reports, spec proposals.

## Session report — the ledger of why

The session report in `logs/sessions/` is the ledger that carries decisions, rationale,
rejected options, and open questions that don't belong in `spec/` or `src/`. Each stage
appends to it.

Required sections:
- **Goal** — what this session is trying to achieve
- **Phase** — current phase
- **Decisions** — choices made and why, linking spec sections
- **Steps** — logged in real time, not reconstructed at the end
- **Gate results** — each gate test run and its outcome (pass/fail + output)
- **Open / next** — blockers and what comes after

Update in real time. A missing or reconstructed-after-the-fact session report is a build
failure.

## Gate exit codes must be shown

Never claim a test passed without running it and showing the output. Every phase gate
result — pass or fail — is recorded in the session report with the actual command output.
"It should work" is not a result.

## The analyser reads reality

The analyser's inputs are:
- `logs/runtime/` — behavior, traces, errors, timings
- Test and gate results — what passed, what flaked, what's slow
- Build behavior — how long generations take, where agents stall or repeat
- The user's own prompts and history — stated and revealed goals, recurring frustrations

The analyser produces findings in `logs/analysis/`. When outcome diverges because the
**goal** was wrong, it proposes a concrete `spec/` amendment for the reviewer and human
to approve — it never silently edits the goal.

## Drift signals — when to invoke the analyser

The analyser holds a standing observation mandate but acts on signals. Invoke it:
- At every phase gate
- On material signals: errors, failing/flaky tests, slow generations, repeated user
  frustration in the prompts

## A build is not done until logs reconcile

The loop closes when `spec ↔ src ↔ logs` agree and the analyser has nothing outstanding.
A system that runs but whose logs diverge from the spec is not done.

## Phase tracking in git

Commit message prefix `phase-N:` makes phase history scannable:
```
git log --oneline | grep "phase-"
```
The current phase is recorded in both the active session report and the commit messages.
