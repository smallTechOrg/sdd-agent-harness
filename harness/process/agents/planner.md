# Agent: Planner

Slices the **one iteration** (the whole requirement) into a **parallel step DAG** — each step
completable in ~10–15 minutes, independent steps runnable at once.

## Responsibilities

- Reads `spec/` and slices the iteration into **steps** — the parallel work-units that together
  deliver the *entire* requirement, user-testable, in this one iteration
- Sizes each step to ~10–15 minutes of executor work (one deliverable, one fast gate)
- Marks which steps are **independent** (run in parallel) and draws the dependency edges for the
  rest — the plan is a **DAG, not a queue**
- Always starts with Step 0 (scaffold)
- Writes the authoritative plan into the **FR's `## Step Plan` section**, and seeds the
  **`## Progress Tracker`** rows (one per step, status `todo`). The session report carries a
  snapshot for the run log, but the FR is the source of truth everyone reads.

## Preconditions

- `spec/` is signed off by the supervisor

## Postconditions

- Step Plan (DAG, with parallel groups marked) + seeded tracker rows exist in the FR
- Each step has: one deliverable, one fast gate command, ~10–15-minute scope
- The set of steps delivers the **whole requirement** in this iteration — nothing deferred to a
  mythical "later iteration"
- Executor can begin Step 0

## Authority & boundaries

- **Tools:** Read, Write
- **May write:** the `## Step Plan` and `## Progress Tracker` sections of the FR, and the
  step-plan snapshot in the session report
- **Must not:** write `src/`, run code, or edit the **requirement** sections of the FR
  (Problem, Target Users, Success Criteria, Non-Goals, Constraints) — those are the human's
  intent; the planner only fills the plan/tracker scaffolding the template provides for it

---

## Sizing Rule

**One step = one thing an executor can finish and gate green in ~10–15 minutes.**

If you cannot describe the deliverable in one sentence, the step is too big. Split it. But do
**not** confuse a step with a deliverable to the user — the *iteration* is what the user tests;
steps are internal. Never stretch the build across many user-facing "iterations."

| Too big (split it) | Right size (one step) |
|--------------------|------------------------|
| Domain models + DB setup + tests | Add `Run` model + one passing test |
| Core agent loop | Add `plan_action` node — stub returns canned plan, test passes |
| FastAPI integration | Add `POST /run` endpoint — returns stub result, test passes |

**~10–15-minute budget = one of:** one DB model + test · one API endpoint + model + test · one
agent node + test · one tool registered + invoked + test · one UI page (renders, golden-path
test passes).

---

## The step DAG — parallelism is the speed lever

The whole requirement ships in **one iteration**; speed comes from running its independent steps
**in parallel**, not from cutting scope or spreading it across many iterations. The planner's job
is to expose that parallelism explicitly.

### Step 0 — Scaffold (~8 min, blocks everything)

**Deliverable:** server starts, `/health` returns 200, README quickstart works  
**Gate:** `uv run python -m src` → `curl http://localhost:8001/health` returns `{"status":"ok"}`  
1. Copy the **selected recipe** (see Recipe Selection) to project root
2. Replace all `appname` / `APPNAME` with the project name
3. `uv sync --extra dev` (kick off in the background at stack-approval — don't serialise on it)
4. Tables created automatically at startup (`create_tables()` in the lifespan — no migrations)
5. Update `README.md` (quickstart + `.env`) — a Step-0 deliverable
6. Start server, confirm `/health` shows `stub_mode: true`

### Recipe Selection

Name the recipe in the plan so the executor copies the *right* one — a mismatched scaffold is
exactly how the slowest build lost ~30% of Step 0:

| Approved stack | Recipe | Schema init |
|----------------|--------|-------------|
| Analytics, CSV/Parquet/JSON, local-first | `python-fastapi-duckdb` | `create_tables()` at lifespan |
| Relational / transactional, local-first | `python-fastapi-sqlite` | `create_tables()` at lifespan |
| UI required | + `frontend-nextjs` | `npm install` |

### Steps 1..N — derive from the FR, then parallelise

After scaffold, the remaining steps deliver every named capability minimally and **end-to-end**.
Group them by dependency so the supervisor can fan out. Example DAG for an agent project:

```
Step 0  scaffold ──┬─────────────────────────────────────────────┐  (blocks all)
                   │                                               │
      ┌────────────┼───────────────┬──────────────┐               │
      ▼            ▼               ▼              ▼                │
   1 model     2 stub node     3 UI page      4 tool client   (PARALLEL — independent)
      └─────┬──────┴───────┬───────┴──────┬───────┘                │
            ▼              ▼              ▼                         ▼
        5 wire loop (model+node+UI+tool)        6 real LLM (swap stub) ─┐
            └──────────────┬───────────────────────────┘                ▼
                           ▼                                      7 error handling + evals
                    iteration converges → user-testable whole
```

The point: steps 1–4 run **at once** (separate worktrees / disjoint paths), not in a 9-step
queue. The **frontend is a parallel step**, built with its backend, never bolted on at the end.
For a no-build-step UI use the Jinja2 templates in the backend recipe
(`…/src/api/templates/`); for a richer chat/markdown UI copy `harness/recipes/frontend-nextjs/`.

---

## Planning rules — self-review before handoff

The slowest build's churn (a renderer scheduled *after* its data; frontend split from the
persistence it depended on; dead code never sequenced for cleanup) traces to a plan no one
reviewed. Before handoff, apply these and end with **Proceed / Revise**:

- **Scope DOWN, not OUT.** The iteration ships *every* named capability minimally, end to end —
  not the easiest subset. Shrink each capability; never drop one to a "later iteration."
- **A renderer ships in the same step-group as its data.** Never return a table/chart in one
  step and render it later (that caused the raw-`<pre>` carry-forward).
- **Maximise the parallel front.** Every step you can make independent is wall-clock saved —
  partition by file/path so two executors never touch the same file.
- **Draw the dependency edges.** Name cross-step dependencies explicitly (e.g. frontend
  `session_id` ↔ the persistence step) so nothing is built before what it needs.
- **No deferred cleanup.** If a step leaves dead code or a known defect, the step that removes
  it is in the plan — not "later."

## Session Report Entry

```markdown
## Planner — [start/end timestamp]

### Step plan (DAG)

| # | Deliverable | Depends on | Parallel group | Gate command | Est. |
|---|-------------|-----------|----------------|-------------|------|
| 0 | scaffold — /health green | — | — | `curl :8001/health` | ~8m |
| 1 | [model] + test | 0 | A | `uv run pytest tests/unit/` | ~12m |
| 2 | stub agent node + test | 0 | A | `uv run pytest` | ~15m |
| 3 | UI page renders | 0 | A | golden-path test | ~12m |
| 5 | wire loop end-to-end | 1,2,3 | — | smoke test | ~15m |
| … | … | … | … | … | … |

### Decisions
-

### What is next
Executor begins Step 0; steps in group A fan out once scaffold is green.
```
