# Workflow: Build

`researcher → planner → executor → reviewer → deployer → analyser ↺`

The build workflow takes a user brief from zero to a working, reviewed, deployed slice.
The pipeline runs autonomously after the one human-touch gate; the analyser closes the
loop back to the head on drift.

---

## Blackboard — what each stage reads and writes

| Stage      | Reads                       | Writes                              |
|------------|-----------------------------|-------------------------------------|
| researcher | user's brief                | `spec/`                             |
| planner    | `spec/`                     | phase plan (session report)         |
| executor   | `spec/`, phase plan         | `src/`, unit tests                  |
| reviewer   | `spec/`, `src/`             | acceptance tests, sign-off          |
| deployer   | `src/`, config              | deploy manifest, deploy result      |
| analyser   | `spec/`, `src/`, `logs/`    | `logs/analysis/`, spec proposals    |

Sub-agents share no memory between invocations. Coordination is through durable
artefacts on disk — not conversation.

---

## Stages

### 1. researcher — get the goal right

Elicits requirements from the user. The supervisor poses questions to the human (only the
main session owns the human channel) and reviews each draft. Elicit enough to act — not
exhaustively; the loop catches the rest. The executor spot-checks feasibility; the
reviewer checks testability and end-user fit.

**Gate (supervisor):** spec is coherent and feasible, no blocking gaps. After sign-off
the pipeline runs autonomously, gated only by tests.

### 2. planner — slice by value

Slices the work into phases by end-user value — smallest end-to-end slice with the
highest value first. No fixed phase list; phases are derived from the spec. Records
phases and their gate tests in the session report.

### 3. executor — make the action

Implements the current phase in `src/` — exactly what the slice calls for, no more.
Every external call (LLM, DB, API) sits behind a thin abstraction. The skeleton phase
runs fully offline with stubs; the gate must pass with no API key set.

### 4. reviewer — guard the goal

Reviews `src/` against the spec. Guards verification — tests are the executable form of
the spec. Signs off the phase gate. Highest bar; nothing passes without reviewer
sign-off.

**Pre/postconditions:** unit tests pass before the reviewer starts; acceptance tests and
sign-off exist before the deployer starts.

### 5. deployer — ship it

Deploys the current phase locally (demo server) or to the target environment. Records
the deploy result in the session report. Deploy to production is a later phase.

### 6. analyser — close the loop

Reads `logs/`, tests, and gate results. Compares outcome against goal:

| Drift       | Correction                                        |
|-------------|---------------------------------------------------|
| spec ≠ src  | route back to executor                            |
| src ≠ logs  | route to fix workflow                             |
| logs ≠ spec | fix src/, or propose spec amendment if goal wrong |

Exits when `spec ↔ src ↔ logs` agree and nothing is outstanding. Never silently edits
the goal — spec amendments go to the reviewer and human for approval.

---

## Session report

Each stage appends to `logs/sessions/YYYY-MM-DD-HHMMSS-<branch>.md` — decisions,
rationale, gate results, open questions. The ledger carries the *why* that doesn't
belong in `spec/` or `src/`.
