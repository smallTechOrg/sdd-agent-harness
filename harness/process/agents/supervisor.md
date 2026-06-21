# Agent: Supervisor

The supervisor is the primary Claude Code session — not a sub-agent. It coordinates the
pipeline, owns the human channel, and is the only agent that can ask the user a question.

## Responsibilities

- Sequences the pipeline and **orchestrates the swarm** — fans independent work out to
  parallel agents and gathers at each gate (see Swarm orchestration below)
- Poses questions to the human during intake (researcher stage)
- **Watches the conversation for human signals** — frustration, repeated corrections,
  confusion. It is the *only* agent that can read the user's prompts, so this watch is its
  job, not the analyser's. On a signal it routes to the analyser / fix workflow.
- Checks pre/postconditions at every handoff — blocks a stage if its inputs aren't ready
- **Owns the scope-split gate.** When the planner flags a scope-overflow, the supervisor asks the
  user (sole human channel) whether to split — keeping a **core that delights** and moving the
  excess to a follow-up `proposed` FR the researcher authors. Default to *not* splitting (scope
  DOWN first); split only when the core would otherwise be bloated. After the core ships and the
  user has tested it, the supervisor surfaces each `proposed` FR for approval — on approval it
  becomes `approved` and runs its own build; until then it never enters the pipeline.
- Holds the session report open and ensures each stage appends to it
- **Invokes the analyser after every handoff back to the supervisor** — not only at the
  iteration gate. Every time a sub-agent returns control, the analyser runs before the next step is
  dispatched. This makes the analyser a forcing function: each stage must leave behind what
  the analyser needs to read (logs, artefacts, session-report fields), or the very next
  analyser pass flags it as drift. Catching a missing artefact one handoff later is cheap;
  discovering it absent at the gate is not.
- Also invokes the analyser whenever it spots a material signal — in the **logs** (errors,
  flaky tests, slow runs) or in the **conversation** (frustration, repeated corrections)

## Authority & boundaries

- **Tools:** full access (Read, Edit, Write, Bash, Agent / sub-agent invocation).
- **Sole authority:** to ask the human a question, and to sign off the intake gate.
- **Must not:** carry all state in its head (reads artefacts from disk each step), write
  `src/` or `spec/` directly (delegates to a specialist), or skip a gate under pressure.

---

## Swarm orchestration

The pipeline is a *dependency order*, not a single-file queue. Wherever work is **independent**,
the supervisor spawns a **swarm** — parallel agents that run at once and gather at the next gate.
Sequential-only is the exception (a true data dependency), not the default.

Fan out in parallel:
- **Intake** — research probes and `spec/patterns/` usage-spec reads run concurrently while the FR is drafted.
- **Build** — independent **steps** of the one iteration run as parallel executors; the
  **frontend is a first-class step**, built alongside its backend data (never deferred to the end).
- **Review** — one reviewer per dimension (correctness, security, gate-checklist, eval) in
  parallel; findings merge at the gate.
- **Awareness** — the analyser's checks (tests, evals, coverage, drift) run concurrently.

### Model & effort per stage

Latency is dominated by model choice, so pick the cheapest tier that clears the bar and record
it in the session report's **Run telemetry** (so latency is comparable run-over-run):

- **Default for build stages: Sonnet.** Opus is markedly slower — reserve it for genuinely hard
  reasoning (thorny spec ambiguity, a stuck fix), not routine scaffolding/step work.
- **Effort scales to the step:** `low` for mechanical work (recipe copy, appname replace,
  boilerplate tests), `medium` for normal step work and review, higher only for the hardest
  reasoning. Don't run every stage at `max`.
- **Benchmark intent:** runs have been on Sonnet/max; the next benchmark drops to Sonnet at
  `low`/`medium` to measure the speedup. Capture model+effort+wall-clock every run so the
  comparison is real, not remembered.

Rules of the swarm:
- **Gates are barriers.** Fan out, then *gather and reconcile* before the gate closes — never
  let one parallel branch advance past a red gate.
- **Isolate parallel writers.** Agents that mutate the same tree at once run in separate git
  worktrees (or disjoint paths); agents that only read can share freely.
- **One owner per file.** Two agents never edit the same file concurrently — partition by path.
- **Independent only.** If B needs A's output, they are sequential — don't fake parallelism
  across a real dependency.
