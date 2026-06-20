---
description: The mechanical definition of done — the demo and productionise gate scripts whose exit code is the verdict.
---

# Workflow: Gates — the mechanical definition of done

"Done" is not an opinion, a green badge, or "looks right." **Done = the gate script exits `0`.** This file
is the exact script. There are two gates, two tiers (`harness.md` § Done):

- **DEMO** (local, the `/build` finish line) — the agent boots, answers for real, and the answer is *right*.
- **PROD** (the `/deploy` finish line) — everything the demo proves, plus it proves on Postgres and as a
  reachable artifact.

PROD is a strict superset of DEMO. Never claim either passed without running it (`harness.md` § honest).
A real run needs a funded `APP_LLM_API_KEY` (`agent/config.py`).

This gate is the repo's one defensible edge (`COMPETITIVE-RESEARCH.md` §3): the only spec-driven tool
that **compiles and proves it ran** — every acceptance criterion is bound to an executable check, and
*done* means the agent booted and gave the right answer. Three things keep that claim honest, and none
may be weakened: the **`[@eval]` lint** (a criterion with no resolvable check is a build failure, not a
TODO), **judge-stability** (the outcome judge is multi-sampled with margin so exit-0 is deterministic,
not a coin-flip — §5 of the critique), and the **two-turn run** (a follow-up that errors fails the gate
even if the first turn was perfect).

---

## DEMO gate — eight checks, all mechanical

Each line below is one command whose exit code is the verdict; the gate is their `&&`. None is prose.

| # | Check | How it's proven |
|---|-------|-----------------|
| 1 | **`[@eval]` lint** | every EARS line in `spec/capabilities/*.md` carries an `[@eval: path::case]` token that resolves to a real test/case. An unbound criterion **fails the build** (`COMPETITIVE-RESEARCH.md` §5.2). Run first — cheapest, and it is the differentiator. |
| 2 | **Suite passes (real key)** | `uv run pytest` — the FakeModel loop tests + the `test_demo_gate` judge test + the Playwright journey test (`patterns/observability-and-evals.md`, `patterns/interface.md`). Loose asserts (≥2 iterations, tool spans present, force_finalize) — a live model's wording varies; the *outcome eval*, not a string match, judges correctness. |
| 3 | **Server boots** | start `python -m agent` (`agent/__main__.py` → uvicorn on `settings.port`), wait for it to answer. |
| 4 | **`/health` 200** | `curl -fsS localhost:$PORT/health` returns `{"ok":true}` (`agent/server.py`). |
| 5 | **Two-turn run completes** | `POST /runs {goal}` (Q1) → `status == "completed"`, then `POST /runs {goal:<follow-up>, session_id:<same>}` (Q2) on the **same session** → also `completed`. **Any Q2 error fails the gate**, even if Q1 was perfect (`SPEC-RECONCILIATION.md` C3, decision #12). A 500 or `status != completed` on either turn fails. |
| 6 | **Outcome (judge-stable) + trajectory eval pass** | the run's answer scores against its EARS criterion — **multi-sampled** (the judge is run *N* times; pass requires the margin-protected mean `≥ threshold − margin`, and the spread is reported so a flaky borderline verdict is visible, not a coin-flip) — **and** the persisted spans show the right path (`stable_outcome_eval` + `trajectory_eval`). A **200 with a wrong answer fails here.** |
| 7 | **UI journey (Playwright)** | the post-JS DOM shows the real answer after the run completes, with **no console error**, invariant asserts, **bounded retries** so it never flakes (`patterns/interface.md` Gate, decisions #5/#10). Headless products skip this; every build with a UI ships it. |
| 8 | **Traces present** | `/traces` renders ≥1 run with spans for that run (`agent/observability.py`, the `spans` table). No spans = not observable = fail. |

Checks 5–8 share the same real run: submit Q1+Q2, read `status`, judge the answer, render the UI, confirm
the spans landed. Don't re-run the model per assertion — one two-turn session, several assertions (the
**judge** in check 6 is the deliberate exception: it is multi-sampled, on the already-produced answer).

### `make gate` / `make demo-gate`

```makefile
PORT     ?= 8001
GOAL     ?= How long do refunds take?
FOLLOWUP ?= And how do I start one?

demo-gate: gate            # alias
gate:
	python -m agent.eval_lint                                      # 1 — [@eval] lint: every EARS line bound
	uv run pytest -q                                              # 2 — suite (real key, loose asserts) + Playwright
	@bash scripts/demo_gate.sh $(PORT) "$(GOAL)" "$(FOLLOWUP)" # 3-8 — boot, health, two-turn, judge, UI, traces
```

The `[@eval]` lint runs **twice** by design — as the explicit makefile step 1 (so a missing binding fails
fast before the suite starts) and again inside `uv run pytest` via `tests/test_eval_lint.py` (a one-line
`assert agent.eval_lint.main() == 0`), so the binding is enforced whether the gate runs as `make gate` or
as a bare `pytest`. The judge-stable `test_demo_gate` is check 6's in-process twin in the same suite. Belt
and suspenders: neither the binding nor the outcome check can silently slip through one entry point.

### `scripts/demo_gate.sh` (runnable sketch — adapt the JSON paths to your spec)

```bash
#!/usr/bin/env bash
# DEMO gate checks 3-8 (1 = eval_lint, 2 = pytest run before this). Exit 0 = done.
# Generate fresh per project; this is the shape.
set -euo pipefail
PORT="${1:-8001}"; GOAL="${2:-How long do refunds take?}"; FOLLOWUP="${3:-And how do I start one?}"
BASE="http://localhost:${PORT}"
: "${APP_LLM_API_KEY:?fund a key for a real run}"        # no key -> no gate

# 3 — boot the server in the background, ensure we kill it on any exit
python -m agent & SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# 4 — wait up to 30s for /health 200
for i in $(seq 1 30); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then break; fi
  sleep 1
  [ "$i" = 30 ] && { echo "FAIL: /health never came up"; exit 1; }
done
curl -fsS "${BASE}/health" | grep -q '"ok": *true' || { echo "FAIL: /health not ok"; exit 1; }

# 5 — TWO-TURN run on one session. Q1 then a follow-up Q2; ANY Q2 error fails the gate.
SID="gate-$(date +%s)"
R1="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' \
      -d "$(jq -n --arg g "$GOAL" --arg s "$SID" '{goal:$g, session_id:$s}')")"
echo "$R1" | jq -e '.status == "completed"' >/dev/null \
  || { echo "FAIL: Q1 did not complete: $R1"; exit 1; }
RUN_ID="$(echo "$R1" | jq -r '.run_id // .id')"
R2="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' \
      -d "$(jq -n --arg g "$FOLLOWUP" --arg s "$SID" '{goal:$g, session_id:$s}')")" \
  || { echo "FAIL: Q2 (follow-up on same session) errored"; exit 1; }
echo "$R2" | jq -e '.status == "completed"' >/dev/null \
  || { echo "FAIL: Q2 did not complete on the same session: $R2"; exit 1; }

# 6 — outcome (judge-stable, multi-sampled) + trajectory eval on the Q1 run
python -m agent.gate_eval --run-id "$RUN_ID" --goal "$GOAL" \
  || { echo "FAIL: eval gate (outcome below threshold-with-margin, high judge variance, or bad trajectory)"; exit 1; }

# 7 — UI journey (skip with UI_E2E=0 for a headless product)
if [ "${UI_E2E:-1}" = "1" ]; then
  uv run pytest tests/e2e/test_primary_journey.py -q \
    || { echo "FAIL: Playwright UI journey (post-JS DOM / console error)"; exit 1; }
fi

# 8 — traces present for the Q1 run
curl -fsS "${BASE}/traces" | grep -q "$(echo "$GOAL" | head -c 12)" \
  || { echo "FAIL: run not visible at /traces"; exit 1; }

echo "DEMO GATE PASS"          # the only success signal is exit 0
```

### `agent.eval_lint` (check 1 — the `[@eval]` binding lint, callable standalone)

The cheapest check and the actual differentiator: parse every EARS line in `spec/capabilities/*.md`,
require an `[@eval: path::case]` token, and confirm the referenced test exists and names that case. A
criterion with no resolvable check is a **build failure**, not a TODO — this is what makes "every
acceptance criterion is bound to an executable check" a fact the gate enforces, not a slogan
(`COMPETITIVE-RESEARCH.md` §5.2, `workflows/build.md` §2a/§2).

```python
# agent/eval_lint.py — exit 0 iff every EARS line is bound to a resolvable [@eval].
import pathlib, re, sys
EARS = re.compile(r"\bSHALL\b")
TOKEN = re.compile(r"\[@eval:\s*([^\]:]+)::([^\]]+)\]")

def main() -> int:
    problems = []
    for f in pathlib.Path("spec/capabilities").glob("*.md"):
        text = f.read_text()
        # one [@eval] may sit on the EARS line or the line directly under it
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if not EARS.search(ln):
                continue
            window = ln + ("\n" + lines[i + 1] if i + 1 < len(lines) else "")
            m = TOKEN.search(window)
            if not m:
                problems.append(f"{f}:{i+1}  EARS line has no [@eval] token"); continue
            path, case = pathlib.Path(m.group(1).strip()), m.group(2).strip()
            if not path.exists() or case not in path.read_text():
                problems.append(f"{f}:{i+1}  [@eval] unresolved: {path}::{case}")
    for p in problems:
        print(f"EVAL-LINT FAIL: {p}", file=sys.stderr)
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
```

### `agent.gate_eval` (the eval half, judge-stable, callable from the script)

Wraps the proven `stable_outcome_eval` + `trajectory_eval` (`patterns/observability-and-evals.md`) — it does
**not** re-implement multi-sampling, it calls the one judge-stability function that recipe owns — and exits
non-zero on failure so the shell `&&` chain breaks. The criterion and `expect_tools` come **from the spec**
(`spec/capabilities/*.md` EARS line → `criterion`; its acceptance bullets → `evaluation_steps` /
`expect_tools`) — one EARS line ⇒ one outcome assertion + one trajectory assertion. Generate the per-spec
arguments at build time; the runner below is constant.

**Judge-stability — why exit-0 is deterministic, not a coin-flip.** The outcome eval is an LLM judge, the
same non-deterministic class we mock elsewhere (`COMPETITIVE-RESEARCH.md` §4). Left raw it makes "exit 0 =
done" *probabilistic* and threshold-sensitive — the gate's one soft spot. `stable_outcome_eval` defangs it
(§5 of the critique): **multi-sample** the judge (`samples`, e.g. 5) and pass only on the **margin-protected
mean** (`mean ≥ threshold − margin`), while **reporting the spread** (max−min) so a flaky, borderline verdict
is *visible* in the gate output instead of being silently rounded away. A run that scores 4,4,4,4,4 passes
cleanly; one that scores 5,5,4,2,3 (mean 3.8) surfaces its wide spread for review rather than sliding through
on a lucky single draw.

```python
# agent/gate_eval.py — exit 0 iff the run's answer is RIGHT-with-margin-and-stable AND the path is sane.
import argparse, asyncio, sys
from sqlalchemy import select
from .db import get_sessionmaker, Run
from .evals import stable_outcome_eval, trajectory_eval   # the ONE judge-stability impl (observability-and-evals.md)

# Filled from the spec at build time (one block per capability under test).
CRITERION = "WHEN asked about refund timing the system SHALL state 5 business days."
EVALUATION_STEPS = ["Does the answer mention refunds?",
                    "Does it state 5 business days?",
                    "Is it free of contradicting timelines?"]
EXPECT_TOOLS = ["search_docs"]
FORBID_TOOLS = []                       # e.g. mutating tools that must not fire ungated

SAMPLES, THRESHOLD, MARGIN = 5, 4, 0.5   # judge-stability knobs (keep in the spec, not magic)

async def main(run_id: str, goal: str) -> int:
    async with get_sessionmaker()() as s:
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
    # multi-sample the judge on the SAME answer (the run is not repeated) via the proven recipe.
    outcome_ok, mean, detail = await stable_outcome_eval(
        goal, run.answer, CRITERION, EVALUATION_STEPS,
        threshold=THRESHOLD, samples=SAMPLES, margin=MARGIN)
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)
    print(f"OUTCOME scores={detail['scores']} mean={mean:.2f} spread={detail['spread']} "
          f"(need mean≥{THRESHOLD - MARGIN})", file=sys.stderr)
    if not outcome_ok:
        print("OUTCOME FAIL: below threshold-with-margin or unstable (high judge variance)", file=sys.stderr)
    if not ok_t:
        print(f"TRAJECTORY FAIL: {reasons}", file=sys.stderr)
    return 0 if (outcome_ok and ok_t) else 1

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True); p.add_argument("--goal", required=True)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.run_id, a.goal)))
```

`uv run pytest` (check 2) also runs `test_demo_gate` (`patterns/observability-and-evals.md`), which does the
same outcome+trajectory assertion in-process, plus the Playwright journey (check 7). The script's run is the
**end-to-end** proof over HTTP — same verdict, exercised through the real server and the real browser.

---

## PROD gate — DEMO + four more, on the artifact

PROD assumes DEMO passed, then proves the same agent on the productionise rung (`patterns/deploy.md`). The
async stack means **no code changes between rungs — only `APP_DATABASE_URL` flips** (`agent/config.py`).

| # | Check | How it's proven |
|---|-------|-----------------|
| P1 | **Suite passes on Postgres** | flip `APP_DATABASE_URL` to a throwaway `postgresql+asyncpg://…`, re-run `uv run pytest`. Same suite, real DDL/JSON behaviour. NEVER psycopg2. |
| P2 | **Artifact builds** | `langgraph build -t $IMG .` **or** `docker build -t $IMG .` succeeds (`patterns/deploy.md`). |
| P3 | **Reachable URL** | the deployed container answers `GET /health` 200 **and** the real two-turn run completes + its judge-stable outcome eval passes — DEMO checks 4-6, against the live URL. |
| P4 | **No secret leaks** | `git grep` / image-context scan finds no key in the build context, and no credential reaches the prompt (`patterns/deploy.md` § Secrets). |

### `make prod-gate`

```makefile
PG_URL ?= postgresql+asyncpg://localhost/agent_gate_test
IMG    ?= my-agent:gate
URL    ?= http://localhost:8001        # set to the deployed URL after deploy

prod-gate: gate                        # P0 — DEMO must pass first
	APP_DATABASE_URL="$(PG_URL)" uv run pytest -q          # P1 — same suite on Postgres
	docker build -t $(IMG) . || langgraph build -t $(IMG) . # P2 — artifact builds
	@bash scripts/prod_gate.sh "$(URL)"           # P3 — reachable URL: health + real run + eval
	@! git grep -nE 'sk-[A-Za-z0-9]|APP_LLM_API_KEY=[^$$]' -- ':!*.md' \
	  || { echo "FAIL: secret in tracked files"; exit 1; } # P4 — no secret leaks
```

`prod_gate.sh` is `demo_gate.sh`'s health + two-turn run + judge-stable eval + traces block (checks 4-8)
pointed at the deployed `URL` instead of a locally-booted server — the same assertions, no duplicated logic.
P1's Postgres run reuses the conftest create_all/drop_all-per-test fixture (`patterns/react-agent.md` gate
harness); on a real prod DB use **Alembic migrations**, not auto-`create_all` — that sequence lives in
`workflows/deploy.md` and `patterns/persistence.md` (§ Migrations), never in Phase 1.

---

## What the gate is NOT

- **Not a status check.** A `200` with a wrong answer **fails** — that's the entire reason the judge-stable
  outcome eval (check 6) sits between "run completed" and "done" (`patterns/observability-and-evals.md`).
- **Not a slogan.** "Every criterion is bound to a check" is enforced by the `[@eval]` lint (check 1); an
  unbound EARS line fails the build, so the claim is a fact, not marketing (`COMPETITIVE-RESEARCH.md` §5).
- **Not a green CI badge.** CI, if any, just runs this same script; the truth is its exit code, never the
  badge (`patterns/deploy.md` § CI is opt-in).
- **Not prose.** "I tested it and it works" is not a pass. `echo $?` after `make gate` is the pass.

## Run it

```bash
make gate          # DEMO  — the /build finish line
make prod-gate     # PROD  — the /deploy finish line; runs DEMO first
echo $?            # 0 = done. Anything else = not done.
```

→ `workflows/build.md` invokes `make gate`; `workflows/deploy.md` invokes `make prod-gate`.
