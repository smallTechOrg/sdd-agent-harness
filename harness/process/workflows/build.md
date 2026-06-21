# Workflow: Build

`researcher → planner → executor → reviewer → deployer → analyser ↺`

Takes a user brief from zero to a working, reviewed, locally deployed agent.
Runs as a sequence of **~15-minute iterations** — after each one the system is runnable.
The pipeline is autonomous after the one human-touch approval gate.

---

## Blackboard — what each stage reads and writes

| Stage      | Reads                            | Writes                                          |
|------------|----------------------------------|-------------------------------------------------|
| researcher | user's brief                     | `spec/features/FR-NNN.md`, `spec/rules/`        |
| planner    | `spec/`                          | iteration plan (session report)                 |
| executor   | `spec/`, iteration plan          | `src/`, `tests/`, recipe scaffold               |
| reviewer   | `spec/`, `src/`, `tests/`        | acceptance tests, sign-off (session report)     |
| deployer   | `src/`, config                   | local demo running, result (session report)     |
| analyser   | `spec/`, `src/`, `logs/`         | `logs/analysis/`, spec amendment proposals      |

Sub-agents share no memory. Coordination is through durable artefacts on disk.

---

## Stages

### 1. researcher — get the goal right

Runs the intake script (`harness/process/agents/researcher.md`):
- Round 1: 4 core questions — problem, users, success criteria, constraints
- Round 2: 4 detail questions — integrations, non-goals, data shape, first runnable milestone
- Round N: adaptive until FR is complete or user accepts the risk of gaps
- Proposes tech stack; user approves
- Collects all API keys before sign-off; records which are present (boolean) in session report
- Writes `spec/features/FR-NNN.md` from template (`harness/process/templates/FR.md`)
- Fills `spec/rules/tech-stack.md` with the approved stack

**Gate (supervisor):** FR coherent, stack approved, all keys identified.
After sign-off the pipeline runs autonomously, gated by tests and user acceptance.

### 2. planner — slice into 15-minute iterations

Reads the spec and produces an iteration plan where each iteration:
- Has one deliverable (describable in one sentence)
- Has one gate command (runnable in under 30 seconds)
- Takes ~15 minutes of executor work

**Always starts with:**
- Iteration 0: scaffold — `/health` returns 200 (~8 min)
- Iteration 1: first model + migration + unit test (~12 min)

Records the full iteration plan in the session report (see planner agent for format).

### 3. executor — one iteration at a time

Implements exactly one iteration per invocation. No more.

**Iteration 0 steps (always):**
1. Copy `harness/recipes/python/` to the project root
2. Replace all `appname` / `APPNAME` occurrences with the project name
3. `uv sync`
4. `uv run alembic revision --autogenerate -m "init"`
5. `uv run alembic upgrade head`
6. Confirm `curl http://localhost:8001/health` returns 200
7. Commit: `iter-0: scaffold — /health green`

**Subsequent iterations:**
- Write exactly what the iteration plan says — one model, one endpoint, one node, one tool
- Write the test first (or alongside) — never skip it
- Run the gate command; show output in session report
- Commit: `iter-N: [deliverable]`

**On blocker:** three attempts, then route to fix workflow — do not hack around it.

**Python conventions:**
- `src/` holds all application code; `tests/` at root
- External calls sit behind a thin client in `src/integrations/`
- Stubs in `src/integrations/stubs/` — Phase 2 (Iteration 2) runs fully offline
- `APPNAME_LLM_PROVIDER=stub` must be the default until the LLM iteration

### 4. reviewer — guard the goal

Reviews `src/` against the FR after each iteration.

**Gate (all four required before next iteration starts):**
1. Tests pass — output shown in session report
2. Working tree clean and pushed
3. Reviewer signed off
4. Session report updated

### 5. deployer — ship after Iteration 2

After Iteration 2 (stub agent loop), spin up the local demo:
- `uv run python -m src`
- Confirm `http://localhost:8001` serves a live response
- Log curl output in session report

Deploy to Render or other targets only when the user explicitly requests it.
Never deploy to production automatically.
Confirm all irreversible actions with the user before proceeding.

### 6. analyser — close the loop

After each iteration, check: does `src/` match the FR? Do logs match `src/`?

| Signal | Action |
|--------|--------|
| spec ≠ src | route back to executor |
| src ≠ logs | route to fix workflow |
| logs ≠ spec | fix src/ or propose spec amendment |
| all agree | surface to user for acceptance |

**Done signal:** user explicitly accepts the iteration. Never self-declare done.
Spec amendments go to supervisor + user for approval before any change is made.

---

## Session report

Each stage appends to `logs/sessions/YYYY-MM-DD-HHMMSS-<branch>.md`.
Use the template at `harness/process/templates/SESSION.md`.

Per-stage required fields: stage name + timestamp, decisions, gate output, blockers, what is next.
