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

3. **15-minute iterations.** Every unit of work is scoped so the executor can complete it
   in ~15 minutes and leave the system in a runnable, demonstrable state. An iteration
   that cannot be described in one sentence is too large — split it. This is the atomic
   unit of the harness: one deliverable, one gate command, one commit.

4. **Always runnable.** After every iteration, the system must start and serve a request.
   A build that is "almost working" is not working. Partial progress is committed only
   when the gate passes — never mid-iteration.


## Navigation

**[rules/](rules/)** — what the harness enforces
- [non-negotiables.md](rules/non-negotiables.md) — the rules that must survive context compression
- [spec-driven.md](rules/spec-driven.md) — spec-before-code discipline
- [git-and-delivery.md](rules/git-and-delivery.md) — branching, commits, PRs
- [testing.md](rules/testing.md) — gate tests, smoke tests, evidence
- [secret-hygiene.md](rules/secret-hygiene.md) — env vars, keys, `.env`

**[process/](process/)** — how work flows
- [README.md](process/README.md) — agents, workflows, pipeline overview
- [agents/](process/agents/) — supervisor, researcher, planner, executor, reviewer, deployer, analyser
- [workflows/](process/workflows/) — build, fix, deploy
**[layout.md](layout.md)** — repo skeleton, where things go

**[patterns/](patterns/)** — hard-won knowledge
- [working-with-llms.md](patterns/working-with-llms.md) — provider selection, stubs, model lifecycle, error handling
- [observability.md](patterns/observability.md) — logs, session reports, drift signals, the analyser

---

The `.claude/` folder at the repo root is a thin adapter binding this harness to Claude Code.
`harness/` is the source of truth; `.claude/` should never diverge from it.