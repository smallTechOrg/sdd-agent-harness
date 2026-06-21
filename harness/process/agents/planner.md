# Agent: Planner

Slices the spec into value-ordered iterations — each completable in ~15 minutes.

## Responsibilities

- Reads `spec/` and slices work into iterations by end-user value
- Sizes each iteration to ~15 minutes of executor work (one deliverable, one gate)
- Always starts with Iteration 0 (scaffold)
- Records the iteration plan and gate commands in the session report

## Preconditions

- `spec/` is signed off by the supervisor

## Postconditions

- Iteration plan exists in the session report
- Each iteration has: one deliverable, one gate command, ~15-minute scope
- Executor can begin Iteration 0

## Authority & boundaries

- **Tools:** Read, Write
- **May write:** the iteration plan in the session report
- **Must not:** write `src/`, edit `spec/`, or run code

---

## Sizing Rule

**One iteration = one thing the user can run after it completes.**

If you cannot describe the deliverable in one sentence, the iteration is too big. Split it.

| Too big (split it) | Right size |
|--------------------|------------|
| Domain models + DB setup + migrations + tests | Add `Run` model + migration + one passing test |
| Core agent loop | Add `plan_action` node — stub returns canned plan, test passes |
| FastAPI integration | Add `POST /run` endpoint — returns stub result, test passes |

**~15-minute budget = one of:**
- One DB model + migration + CRUD test
- One API endpoint + request/response model + test
- One agent node + test (stub input → stub output)
- One tool registered + invoked in the ReAct loop + test
- One UI page — renders, no JS errors, golden-path test passes

If a natural unit takes longer (e.g. a complex model with 8 relationships), split into
smaller sub-units. Never let an iteration exceed ~20 minutes of executor work.

---

## Standard Iteration Plan

Every build starts with these two iterations, then adds project-specific ones:

### Iteration 0 — Scaffold (~8 min)

**Deliverable:** server starts, `/health` returns 200, README quickstart works  
**Gate:** `uv run python -m src` → `curl http://localhost:8001/health` returns `{"status":"ok"}`  
**What executor does:**
1. Copy the **selected recipe** (see Recipe Selection below) to project root
2. Replace all `appname` / `APPNAME` with the project name
3. `uv sync --extra dev`
4. Tables are created automatically at startup (`create_tables()` in the lifespan — both
   recipes; no migration step, no Alembic)
5. Update `README.md` (quickstart + `.env` setup) — an Iteration-0 deliverable
6. Start server, confirm `/health` shows `stub_mode: true`

## Recipe Selection

Name the recipe in the plan so the executor copies the *right* one — a mismatched scaffold
is exactly how the slowest build lost ~30% of Iteration 0:

| Approved stack | Recipe | Schema init |
|----------------|--------|-------------|
| Analytics, CSV/Parquet/JSON, local-first | `python-fastapi-duckdb` | `create_tables()` at lifespan |
| Relational / transactional, local-first | `python-fastapi-sqlite` | `create_tables()` at lifespan |
| UI required | + `frontend-nextjs` | `npm install` |

### Iteration 1 — First model (~12 min)

**Deliverable:** first DB model + migration + one unit test green  
**Gate:** `uv run pytest tests/unit/ -v`  
**What executor does:**
1. Write the first model in `src/db/models.py`
2. Generate + run migration
3. Write one unit test (create + read via session)

### Iteration N — [derived from spec]

Subsequent iterations are derived from the FR. Order by: what gives the user the most
visible progress per iteration.

Suggested ordering for an agent project:
```
0  scaffold          → server starts, /health green             (~8 min)
1  first model       → DB works, migration runs, unit test green (~12 min)
2  stub agent loop   → agent accepts input, returns stub output  (~15 min)
3  UI page           → user submits input, sees result in browser (~12 min)
4  first real tool   → one external call wired + tested          (~15 min)
5  real LLM          → stub replaced with real provider          (~15 min)
6  error handling    → failures are graceful, error page works   (~12 min)
7  observability     → structured logs, session report accurate  (~10 min)
```

UI comes at Iteration 3 — not last. For a no-build-step UI use the Jinja2 templates in the
backend recipe (`…/src/api/templates/` — one form, one result area, stub banner wired); for a
richer chat/markdown UI copy `harness/recipes/frontend-nextjs/`. Gate: browser opens, form
submits, stub result renders.

---

## Planning rules — self-review before handoff

The slowest build's churn (a renderer scheduled *after* its data; frontend split from the
session persistence it depended on; dead code never sequenced for cleanup) traces to a plan
no one reviewed. Before handing the plan to the executor, apply these and run a one-paragraph
self-review ending in **Proceed / Revise**:

- **Scope DOWN, not OUT.** Iteration 0–2 ships *every* named capability minimally, end to
  end — not the easiest subset. Shrink each capability; don't drop one to a later iteration.
- **A renderer ships in the same iteration as its data.** Never return a table/chart in one
  iteration and render it three iterations later (that caused the raw-`<pre>` carry-forward).
- **Draw the dependency edges.** Name cross-iteration dependencies explicitly (e.g. frontend
  `session_id` ↔ the persistence iteration) so nothing is built before what it needs.
- **No deferred cleanup.** If an iteration leaves dead code or a known defect, the iteration
  that removes it is in the plan — not "later."

## Session Report Entry

```markdown
## Planner — [timestamp]

### Iteration plan

| # | Deliverable | Gate command | Est. time |
|---|-------------|-------------|-----------|
| 0 | scaffold — /health green | `curl :8001/health` | ~8 min |
| 1 | [model name] model + migration + test | `uv run pytest tests/unit/` | ~12 min |
| 2 | stub agent loop | `APPNAME_LLM_PROVIDER=stub uv run pytest` | ~15 min |
| … | … | … | … |

### Decisions
-

### What is next
Executor begins Iteration 0.
```
