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

---

## DEMO gate — six checks, all mechanical

Each line below is one command whose exit code is the verdict; the gate is their `&&`. None is prose.

| # | Check | How it's proven |
|---|-------|-----------------|
| 1 | **Suite passes (real key)** | `uv run pytest` — the FakeModel loop tests + the `test_demo_gate` LLM-judge test (`patterns/observability-and-evals.md`). Loose asserts (≥2 iterations, tool spans present, force_finalize) — a live model's wording varies; the *outcome eval*, not a string match, judges correctness. |
| 2 | **Server boots** | start `python -m agent` (`agent/__main__.py` → uvicorn on `settings.port`), wait for it to answer. |
| 3 | **`/health` 200** | `curl -fsS localhost:$PORT/health` returns `{"ok":true}` (`agent/server.py`). |
| 4 | **One real run completes** | `POST /runs {goal}` → JSON with `status == "completed"` (`agent/runner.py`). A 500 or `status != completed` fails. |
| 5 | **Outcome + trajectory eval pass** | the run's answer scores `≥ threshold` against its EARS criterion (LLM-judge) **and** the persisted spans show the right path — `outcome_eval` + `trajectory_eval` (`patterns/observability-and-evals.md`). A **200 with a wrong answer fails here.** |
| 6 | **Traces present** | `/traces` renders ≥1 run with spans for that run (`agent/observability.py`, the `spans` table). No spans = not observable = fail. |

Checks 4–6 are the same real run: submit the goal, read `status`, judge the answer, confirm its spans
landed. Don't re-run the model three times — one run, three assertions.

### `make gate` / `make demo-gate`

```makefile
PORT ?= 8001
GOAL ?= How long do refunds take?

demo-gate: gate            # alias
gate:
	uv run pytest -q                                    # 1 — suite (real key, loose asserts)
	@bash harness/scripts/demo_gate.sh $(PORT) "$(GOAL)" # 2-6 — boot, health, run, evals, traces
```

### `harness/scripts/demo_gate.sh` (runnable sketch — adapt the JSON paths to your spec)

```bash
#!/usr/bin/env bash
# DEMO gate checks 2-6. Exit 0 = done. Generate fresh per project; this is the shape.
set -euo pipefail
PORT="${1:-8001}"; GOAL="${2:-How long do refunds take?}"
BASE="http://localhost:${PORT}"
: "${APP_LLM_API_KEY:?fund a key for a real run}"        # no key -> no gate

# 2 — boot the server in the background, ensure we kill it on any exit
python -m agent & SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# 3 — wait up to 30s for /health 200
for i in $(seq 1 30); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then break; fi
  sleep 1
  [ "$i" = 30 ] && { echo "FAIL: /health never came up"; exit 1; }
done
curl -fsS "${BASE}/health" | grep -q '"ok": *true' || { echo "FAIL: /health not ok"; exit 1; }

# 4 — one real run; require status == completed, capture run_id + answer
RESP="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' \
        -d "$(jq -n --arg g "$GOAL" '{goal:$g}')")"
echo "$RESP" | jq -e '.status == "completed"' >/dev/null \
  || { echo "FAIL: run did not complete: $RESP"; exit 1; }
RUN_ID="$(echo "$RESP" | jq -r '.run_id // .id')"

# 5 — outcome + trajectory eval on THAT run (reads the spec's EARS criterion + spans)
python -m agent.gate_eval --run-id "$RUN_ID" --goal "$GOAL" \
  || { echo "FAIL: eval gate (outcome score < threshold or bad trajectory)"; exit 1; }

# 6 — traces present for that run
curl -fsS "${BASE}/traces" | grep -q "$(echo "$GOAL" | head -c 12)" \
  || { echo "FAIL: run not visible at /traces"; exit 1; }

echo "DEMO GATE PASS"          # the only success signal is exit 0
```

### `agent.gate_eval` (the eval half, callable from the script)

Wraps the proven `outcome_eval` + `trajectory_eval` (`patterns/observability-and-evals.md`) and exits
non-zero on failure so the shell `&&` chain breaks. The criterion and `expect_tools` come **from the spec**
(`spec/capabilities/*.md` EARS line → `criterion`; its acceptance bullets → `evaluation_steps` /
`expect_tools`) — one EARS line ⇒ one outcome assertion + one trajectory assertion. Generate the per-spec
arguments at build time; the runner below is constant.

```python
# agent/gate_eval.py — exit 0 iff the run's answer is right AND the path is sane.
import argparse, asyncio, sys
from sqlalchemy import select
from .db import get_sessionmaker, Run
from .evals import outcome_eval, trajectory_eval

# Filled from the spec at build time (one block per capability under test).
CRITERION = "WHEN asked about refund timing the system SHALL state 5 business days."
EVALUATION_STEPS = ["Does the answer mention refunds?",
                    "Does it state 5 business days?",
                    "Is it free of contradicting timelines?"]
EXPECT_TOOLS = ["search_docs"]
FORBID_TOOLS = []                       # e.g. mutating tools that must not fire ungated

async def main(run_id: str, goal: str) -> int:
    async with get_sessionmaker()() as s:
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
    ok_o, score, _ = await outcome_eval(goal, run.answer, CRITERION, EVALUATION_STEPS)
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)
    if not ok_o:
        print(f"OUTCOME FAIL: score {score} < threshold", file=sys.stderr)
    if not ok_t:
        print(f"TRAJECTORY FAIL: {reasons}", file=sys.stderr)
    return 0 if (ok_o and ok_t) else 1

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True); p.add_argument("--goal", required=True)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.run_id, a.goal)))
```

`uv run pytest` (check 1) also runs `test_demo_gate` (`patterns/observability-and-evals.md`), which does the
same outcome+trajectory assertion in-process. The script's run is the **end-to-end** proof over HTTP — same
verdict, exercised through the real server.

---

## PROD gate — DEMO + four more, on the artifact

PROD assumes DEMO passed, then proves the same agent on the productionise rung (`patterns/deploy.md`). The
async stack means **no code changes between rungs — only `APP_DATABASE_URL` flips** (`agent/config.py`).

| # | Check | How it's proven |
|---|-------|-----------------|
| P1 | **Suite passes on Postgres** | flip `APP_DATABASE_URL` to a throwaway `postgresql+asyncpg://…`, re-run `uv run pytest`. Same suite, real DDL/JSON behaviour. NEVER psycopg2. |
| P2 | **Artifact builds** | `langgraph build -t $IMG .` **or** `docker build -t $IMG .` succeeds (`patterns/deploy.md`). |
| P3 | **Reachable URL** | the deployed container answers `GET /health` 200 **and** a real `POST /runs` completes + its outcome eval passes — the DEMO checks 3-5, against the live URL. |
| P4 | **No secret leaks** | `git grep` / image-context scan finds no key in the build context, and no credential reaches the prompt (`patterns/deploy.md` § Secrets). |

### `make prod-gate`

```makefile
PG_URL ?= postgresql+asyncpg://localhost/agent_gate_test
IMG    ?= my-agent:gate
URL    ?= http://localhost:8001        # set to the deployed URL after deploy

prod-gate: gate                        # P0 — DEMO must pass first
	APP_DATABASE_URL="$(PG_URL)" uv run pytest -q          # P1 — same suite on Postgres
	docker build -t $(IMG) . || langgraph build -t $(IMG) . # P2 — artifact builds
	@bash harness/scripts/prod_gate.sh "$(URL)"           # P3 — reachable URL: health + real run + eval
	@! git grep -nE 'sk-[A-Za-z0-9]|APP_LLM_API_KEY=[^$$]' -- ':!*.md' \
	  || { echo "FAIL: secret in tracked files"; exit 1; } # P4 — no secret leaks
```

`prod_gate.sh` is `demo_gate.sh`'s health+run+eval+traces block (checks 3-6) pointed at the deployed `URL`
instead of a locally-booted server — the same assertions, no duplicated logic. P1's Postgres run reuses the
conftest create_all/drop_all-per-test fixture (`patterns/react-agent.md` gate harness); on a real prod DB
use migrations, not auto-`create_all` (`patterns/deploy.md` § Migrations).

---

## What the gate is NOT

- **Not a status check.** A `200` with a wrong answer **fails** — that's the entire reason the outcome eval
  (check 5) sits between "run completed" and "done" (`patterns/observability-and-evals.md`).
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
