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

**Deliverable:** server starts, `/health` returns 200  
**Gate:** `uv run python -m src` → `curl http://localhost:8001/health` returns `{"status":"ok"}`  
**What executor does:**
1. Copy `harness/recipes/python/` to project root
2. Replace all `appname` / `APPNAME` with the project name
3. `uv sync`
4. `uv run alembic revision --autogenerate -m "init"` (even if Base has no models yet)
5. `uv run alembic upgrade head`
6. Start server, confirm `/health`

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

UI comes at Iteration 3 — not last. Use the Jinja2 templates from
`harness/recipes/python/src/api/templates/`. One form, one result area, stub
banner already wired. No frontend build step. Gate: browser opens, form submits,
stub result renders.

---

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
