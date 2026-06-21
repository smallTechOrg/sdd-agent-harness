# SDD Harness

A **spec-driven-development (SDD) coding-agent harness**: a disciplined method
for building software with AI, where human intent and machine action stay continuously
reconciled. The core objective is to **minimize the distance between intent and outcome**.


## Spec Driven Development

The harness views the ideal SDD process as made up of four fundamental layers:

| Layer     | Question                                          | Artefacts |
|-----------|---------------------------------------------------|-----------|
| Intention | what should this system do?                       | Spec      |
| Action    | what is the system designed to do?      | Code      |
| Outcome   | what does the system actually do?                 | Logs      |
| Awareness | how do we get the system to do what it should do? | Harness   |

The first three layers (intention, action & outcome) are the **sources of truth** about
the system from different perspectives; the fourth (awareness) is the practice that makes
sense of the truth and corrects course.


## Awareness Loop

    spec (intention) ──▶ code (action) ──▶ logs (outcome)
       ▲                                   │
       └──────────── harness ◀─────────────┘
            observe drift, adjust intention or action




## Principles

1. **Humans author intent.** The core spec is written by the user. The researcher asks
   questions and helps structure it, but the words of core intent are owned by the user.

2. **Spec stays current.** Spec is continuously updated to reflect what the code and logs
   reveal. When they diverge, spec wins — fix the code, or amend the spec first.

3. **One iteration, parallel steps.** An **iteration** delivers the *whole requirement*,
   user-testable — the unit the user accepts (normally one per build). It is built from
   **steps**: ~10–15-min work-units, each one deliverable + one fast gate + one commit, run
   **in parallel** wherever independent. A step that cannot be described in one sentence is too
   large — split it. Speed comes from widening the parallel step front, not from spreading the
   work across many user-facing iterations.

4. **Always runnable.** After every step the system must start and serve a request; at the
   iteration boundary the whole requirement is testable. A build that is "almost working" is not
   working. Partial progress is committed only when a step's gate passes — never mid-step.


## Navigation

**[rules/](rules/)** — what the harness enforces
- [non-negotiables.md](rules/non-negotiables.md) — the rules that must survive context compression
- [spec-driven.md](rules/spec-driven.md) — spec-before-code discipline
- [git-and-delivery.md](rules/git-and-delivery.md) — branching, commits, PRs
- [testing.md](rules/testing.md) — gate tests, smoke tests, evals, evidence
- [secret-hygiene.md](rules/secret-hygiene.md) — env vars, keys, `.env`
- [gotchas.md](rules/gotchas.md) — encoded institutional memory: the traps real builds hit, with stable IDs

**[process/](process/)** — how work flows
- [README.md](process/README.md) — agents, workflows, pipeline overview
- [agents/](process/agents/) — supervisor, researcher, planner, executor, reviewer, deployer, analyser
- [workflows/](process/workflows/) — build, fix, deploy
**[layout.md](layout.md)** — repo skeleton, where things go
**[recipes/](recipes/)** — proven, version-stamped runnable scaffolds (python-fastapi-sqlite, python-fastapi-duckdb, frontend-nextjs)
**[benchmark/](benchmark/)** — the harness self-benchmark: golden briefs + a speed×quality rubric + a trend ledger. Measures whether harness changes make builds faster *and* higher-quality.

**[patterns/](patterns/)** — hard-won knowledge
- [working-with-llms.md](patterns/working-with-llms.md) — provider selection, stubs, model lifecycle, error handling
- [observability.md](patterns/observability.md) — logs, session reports, drift signals, the analyser
- [engineering.md](patterns/engineering.md) — fundamental software-engineering principles
- [usage-specs/](patterns/usage-specs/) — version-pinned API-shape guardrails (fastapi, langgraph, google-genai, …)

---

The `.claude/` folder at the repo root is a thin adapter binding this harness to Claude Code.
`harness/` is the source of truth; `.claude/` should never diverge from it.