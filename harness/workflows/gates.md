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

## DEMO gate — the mechanical checks, all mechanical

Each line below is one command whose exit code is the verdict; the gate is their `&&`. None is prose.

| # | Check | How it's proven |
|---|-------|-----------------|
| 0 | **README present + documents `make gate`** | `README.md` exists (a REQUIRED deliverable — `build.md` §3) and documents the `make gate` entry point a non-tech owner runs (`C-RUNNER-PREFIX`). Cheap mechanical owner for a "Required" file that no check previously verified — a build could otherwise ship zero README and pass green (the "documented, not proven" gap the thesis condemns, HARDENING-LOG iter 8). Run inside `demo_gate.sh` before boot. |
| 1 | **`[@eval]` lint** | every EARS line in `spec/capabilities/*.md` carries an `[@eval: path::case]` token that resolves to a real test/case. An unbound criterion **fails the build** (`COMPETITIVE-RESEARCH.md` §5.2). Run first — cheapest, and it is the differentiator. |
| 2 | **Suite passes (real key)** | `uv run pytest` — the FakeModel loop tests + the `test_demo_gate` judge test + the Playwright journey test (`patterns/observability-and-evals.md`, `patterns/interface.md`). Loose asserts (≥2 iterations, tool spans present, force_finalize) — a live model's wording varies; the *outcome eval*, not a string match, judges correctness. |
| 3 | **Server boots** | start `python -m agent` (`agent/__main__.py` → uvicorn on `settings.port`), wait for it to answer. |
| 4 | **`/health` 200** | `curl -fsS localhost:$PORT/health` returns `{"ok":true}` (`agent/server.py`). |
| 5 | **Two-turn run completes** | `POST /runs {goal}` (Q1) → `.ok == true and .data.status == "completed"` (the `ok()` envelope — read `.data.*`, not the top level), then `POST /runs {goal:<follow-up>, session_id:<same>}` (Q2) on the **same session** → also completed. **Any Q2 error fails the gate**, even if Q1 was perfect (`SPEC-RECONCILIATION.md` C3, decision #12). A 500 or `.data.status != completed` on either turn fails. |
| 6 | **Outcome (judge-stable) eval passes; trajectory advisory** | the run's answer scores against its EARS criterion — **multi-sampled** (the judge is run *N* times; pass requires the margin-protected mean `≥ threshold − margin`, and the spread is reported so a flaky borderline verdict is visible, not a coin-flip). A **200 with a wrong answer fails here.** The persisted-span `trajectory_eval` runs too but is **ADVISORY for a 1-capability v1 slice** — logged, not gate-blocking (a benign fail-soft tool span would else false-RED a correct answer); it is promoted to a hard blocker when a 2nd capability adds a tool-ordering contract (`patterns/observability-and-evals.md` L95-98/197). |
| 7 | **UI journey (Playwright)** | the post-JS DOM shows the real answer after the run completes, with **no console error**, invariant asserts, **bounded retries** so it never flakes (`patterns/interface.md` Gate, decisions #5/#10). The answer assert checks the DOM **contains a real expected value**, not merely `not_to_be_empty()` — a "no data loaded" error is also a non-empty string, so non-empty alone false-greens a wrong-answer journey (HARDENING-LOG iter 7). "A real expected value" means a value derivable deterministically from the **INPUT**. For an **extraction** agent that is a literal token in the resource (the `30 days` example); for a **transform/judgment** agent (code review, summarize, classify, verdict) whose answer paraphrases the input, assert an **input symbol** the model echoes — an identifier, number, or filename from the input — never a brittle paraphrase of the output, and never a non-empty fallback (`patterns/interface.md` § Gate). For a **session-scoped** agent (`C-SESSION-SCOPE`) the journey first fills the upload/paste affordance with the fixture (browser-tier mirror of check 5's `data` field) before asking, else Q1 hits an empty session. Headless products skip this; every build with a UI ships it. |
| 8 | **Traces present** | `/traces` renders ≥1 run with spans for that run (`agent/observability.py`, the `spans` table). No spans = not observable = fail. |

Checks 5–8 share the same real run: submit Q1+Q2, read `status`, judge the answer, render the UI, confirm
the spans landed. Don't re-run the model per assertion — one two-turn session, several assertions (the
**judge** in check 6 is the deliberate exception: it is multi-sampled, on the already-produced answer).

### `make gate` / `make demo-gate`

**`GOAL`/`FOLLOWUP` here and `gate_eval.py`'s `CRITERION` MUST come from the SAME P1 EARS line.** They are two
per-spec edits the builder keeps in sync: DEMO 6 judges the answer to `GOAL` (this Makefile var) against
`CRITERION` (a `gate_eval.py` constant). The defaults below are refund-domain placeholders — **both must be
overridden per build**. Update `GOAL`/`FOLLOWUP` from the P1 capability's trigger + a natural follow-up, and
`CRITERION`/`EVALUATION_STEPS`/`EXPECT_TOOLS` from the SAME P1 EARS line. A half-applied edit (travel
`CRITERION`, refund `GOAL`) runs one domain's goal against the other's rubric — a guaranteed false-RED.
**This is enforced, not just preached:** check 1's `agent.eval_lint` (full/gate mode) asserts `gate_eval.CRITERION`
is a real EARS line in `spec/capabilities/*` and not the refund placeholder, so a `gate_eval.py` left unsynced
fails the gate at step 1 with a named cause — not a downstream "outcome below threshold" pointing at the answer.

```makefile
PORT      ?= 8001
GOAL      ?= How long do refunds take?    # OVERRIDE per build — from the P1 EARS trigger (same line as gate_eval's CRITERION)
FOLLOWUP  ?= And how do I start one?      # OVERRIDE per build — a natural follow-up on the same session
DATA_FILE ?=                              # OVERRIDE to scripts/fixtures/<resource>.<ext> for a SESSION-SCOPED agent
                                          # (C-SESSION-SCOPE); leave UNSET for a key-free/own-data agent

demo-gate: gate            # alias
gate:
	python -m agent.eval_lint                                      # 1 — [@eval] lint: every EARS line bound
	uv run pytest -q                                              # 2 — suite (real key, loose asserts) + Playwright
	@DATA_FILE="$(DATA_FILE)" bash scripts/demo_gate.sh $(PORT) "$(GOAL)" "$(FOLLOWUP)" # 3-8 — boot, health, two-turn, judge, UI, traces
```

**`DATA_FILE` MUST be exported into `demo_gate.sh` (the `@DATA_FILE="$(DATA_FILE)" …` prefix above).** The
script reads `DATA_FILE` from the **environment** (`${DATA_FILE:-}`); a recipe that just runs
`bash scripts/demo_gate.sh …` leaves it unset, so for a session-scoped agent Q1 POSTs `{goal, session_id}`
with **no `data`**, the session is empty, the query tool returns "No `<resource>` loaded", and the
judge-stable outcome eval (check 6) false-REDs a *correct* agent on a 200-with-a-wrong-answer — the exact
failure class the gate exists to catch, here turned against a working build. The Makefile var + the export
are one edit: a data-ingest build sets `DATA_FILE = scripts/fixtures/<resource>.<ext>`; a key-free build
leaves it blank and both turns send just `{goal, session_id}`.

The `[@eval]` lint runs **twice** by design — as the explicit makefile step 1 (so a missing binding fails
fast before the suite starts) and again inside `uv run pytest` via `tests/test_eval_lint.py` (a one-line
`assert agent.eval_lint.main() == 0`), so the binding is enforced whether the gate runs as `make gate` or
as a bare `pytest`. The judge-stable `test_demo_gate` is check 6's in-process twin in the same suite. Belt
and suspenders: neither the binding nor the outcome check can silently slip through one entry point.

### `scripts/demo_gate.sh` (runnable sketch — adapt the JSON paths to your spec)

```bash
#!/usr/bin/env bash
# DEMO gate: check 0 (README) + checks 3-8 (1 = eval_lint, 2 = pytest run before this). Exit 0 = done.
# Generate fresh per project; this is the shape.
set -euo pipefail
PORT="${1:-8001}"; GOAL="${2:-How long do refunds take?}"; FOLLOWUP="${3:-And how do I start one?}"
BASE="http://localhost:${PORT}"
: "${APP_LLM_API_KEY:?fund a key for a real run}"        # no key -> no gate

# 0 — README is a REQUIRED deliverable (build.md §3), so it gets a mechanical owner here, not just prose.
# Cheap check: it exists and references the runner-prefixed gate entry point a non-tech owner follows
# (C-RUNNER-PREFIX). Without this a build could ship ZERO README and pass every other check green — the
# "documented, not proven" gap the harness's own thesis condemns (HARDENING-LOG iter 8).
[ -f README.md ] || { echo "FAIL: README.md is missing (a REQUIRED deliverable — build.md §3)"; exit 1; }
grep -q 'make gate' README.md \
  || { echo "FAIL: README.md does not document \`make gate\` — the gate entry point an owner runs"; exit 1; }

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
# The response is the ok() envelope: {"ok":true,"data":{run_id, status, answer, ...}}. Read .data.*,
# NOT the top level — run_agent's dict carries `status:"completed"` (patterns/interface.md runner.py).
# DATA-INGEST: for an "analyze an uploaded X" agent, Q1 must CARRY the resource (else it answers "no data is
# loaded" and the outcome eval fails). DATA_FILE is read from the ENVIRONMENT — the Makefile `gate` target
# exports it (`@DATA_FILE="$(DATA_FILE)" bash scripts/demo_gate.sh …`); a session-scoped build sets the
# Makefile var to scripts/fixtures/<resource>.<ext> (build.md §3 manifest) so Q1 sends `data` and Q2 reuses it
# from the SAME session (no re-upload — the session-scoped store working, persistence.md). For a key-free/
# own-data agent it stays UNSET and both turns send just {goal, session_id}. A session-scoped build that
# points DATA_FILE at a missing fixture gets a self-diagnosing message below, not a raw `jq --rawfile: No such file`.
DATA_FILE="${DATA_FILE:-}"      # from the env (Makefile exports it); set the Makefile DATA_FILE var per build
SID="gate-$(date +%s)"
Q1_PAYLOAD="$(jq -n --arg g "$GOAL" --arg s "$SID" '{goal:$g, session_id:$s}')"
if [ -n "$DATA_FILE" ]; then
  [ -f "$DATA_FILE" ] || { echo "FAIL: DATA_FILE=$DATA_FILE not found — generate a fixture at scripts/fixtures/<resource>.<ext> (build.md §3) for a session-scoped agent"; exit 1; }
  Q1_PAYLOAD="$(jq -n --arg g "$GOAL" --arg s "$SID" --rawfile d "$DATA_FILE" \
                '{goal:$g, session_id:$s, data:$d}')"   # Q1 carries the uploaded resource
fi
R1="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' -d "$Q1_PAYLOAD")"
echo "$R1" | jq -e '.ok == true and .data.status == "completed"' >/dev/null \
  || { echo "FAIL: Q1 did not complete: $R1"; exit 1; }
RUN_ID="$(echo "$R1" | jq -r '.data.run_id')"
R2="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' \
      -d "$(jq -n --arg g "$FOLLOWUP" --arg s "$SID" '{goal:$g, session_id:$s}')")" \
  || { echo "FAIL: Q2 (follow-up on same session) errored"; exit 1; }
echo "$R2" | jq -e '.ok == true and .data.status == "completed"' >/dev/null \
  || { echo "FAIL: Q2 did not complete on the same session (resource lost?): $R2"; exit 1; }

# 6 — outcome (judge-stable, multi-sampled) + trajectory eval on the Q1 run
python -m agent.gate_eval --run-id "$RUN_ID" --goal "$GOAL" \
  || { echo "FAIL: outcome eval (below threshold-with-margin or high judge variance; trajectory is advisory)"; exit 1; }

# 7 — UI journey (skip with UI_E2E=0 for a headless product). PREREQUISITES the build MUST satisfy first:
#   (a) a runnable ui/ project (ui/package.json with `dev: next dev -p 3001` + react-markdown/remark-gfm,
#       next.config, app/layout.tsx) — see patterns/interface.md § UI prerequisites;
#   (b) the chromium binary: `uv run playwright install chromium` (run in setup, NOT inside the gate).
# Auto-skip with a PRINTED reason if the project was never scaffolded (ui/node_modules absent) so the gate
# fails on a real defect, never on a missing browser/project a non-tech user can't diagnose.
if [ "${UI_E2E:-1}" = "1" ]; then
  if [ ! -d ui/node_modules ]; then
    echo "SKIP check 7: ui/node_modules absent (headless or UI not scaffolded). Run \`cd ui && npm install\` + \`uv run playwright install chromium\` to enable."
  else
    uv run playwright install chromium >/dev/null 2>&1 || true   # idempotent; ensure the browser binary exists
    uv run pytest tests/e2e/test_primary_journey.py -q \
      || { echo "FAIL: Playwright UI journey (post-JS DOM / console error)"; exit 1; }
  fi
fi

# 8 — traces present for the Q1 run. Grep the RUN_ID (rendered VERBATIM, captured in check 5), NOT the goal
# text: server.py renders the goal through _esc() (& < > escaped), so a goal whose first chars contain <, &,
# or > — common for real ticket text like '<urgent> refund …' — would false-fail a raw-substring needle.
curl -fsS "${BASE}/traces" | grep -q "$RUN_ID" \
  || { echo "FAIL: run $RUN_ID not visible at /traces"; exit 1; }

echo "DEMO GATE PASS"          # the only success signal is exit 0
```

### `agent.eval_lint` (check 1 — the `[@eval]` binding lint, callable standalone)

The cheapest check and the actual differentiator: parse every EARS line in `spec/capabilities/*.md`,
require an `[@eval: path::case]` token, and confirm the referenced test exists and **defines a case pytest
would actually collect**. An **EARS line** is one that opens (after an optional list bullet) with an EARS
trigger — `WHEN` / `WHILE` / `IF` / `WHERE` — *and* contains `SHALL`; a prose sentence that merely uses the
word SHALL in a `## What & why` paragraph is **not** a criterion and is ignored, so descriptive spec text
never false-blocks the build (HARDENING-LOG iter 5). Resolution is by **AST** (`ast.parse` → FunctionDef/AsyncFunctionDef names +
parametrize ids), an **exact** match — never a substring scan: a substring scan false-greens a case that
appears only in a `# TODO` comment and a misnamed superset (`test_stub_route_and_more` passing for
`test_stub_route`), so the differentiator could certify a criterion with **zero** executable check behind
it. A criterion with no resolvable, collectable case is a **build failure**, not a TODO — this is what makes
"every acceptance criterion is bound to an executable check" a fact the gate enforces, not a slogan
(`COMPETITIVE-RESEARCH.md` §5.2, `workflows/build.md` §2a/§2).

**Two modes — preflight vs full — by where in the build it runs.** Before code exists (the analyze
preflight, `workflows/build.md` §2a) the test files are not written yet, so existence-checking would be red
on a perfectly good spec. Preflight mode therefore checks only **token presence + `path::case` shape +
uniqueness** (no `path.exists()`). The post-generation gate (DEMO check 1) runs **full** mode, which adds the
existence + case-in-file resolution. Same parser, one flag: `--preflight` skips the file-resolution step.

```python
# agent/eval_lint.py — exit 0 iff every EARS line is bound to a well-formed [@eval].
#   default (full, DEMO check 1): token present AND its path::case resolves to a real, COLLECTABLE test case.
#   --preflight (analyze pre-flight, before code exists): token present + shape + uniqueness only (no path.exists).
import argparse, ast, pathlib, re, sys
# An EARS *criterion* — not any prose sentence that happens to contain SHALL. It must START (after an
# optional list bullet/whitespace) with an EARS keyword AND contain SHALL. This is the load-bearing scope
# fix: spec-writers (and this harness's own _template) phrase descriptive prose as "The agent SHALL be the
# single source of truth…" inside a `## What & why` paragraph; a bare `\bSHALL\b` match treats that prose
# as an unbound criterion and HARD-BLOCKS the build on a sentence (HARDENING-LOG iter 5). Only a line that
# opens with WHEN/WHILE/IF/WHERE (the EARS triggers) is a criterion requiring an [@eval].
EARS = re.compile(r"^\s*-?\s*(WHEN|WHILE|IF|WHERE)\b.*\bSHALL\b")
TOKEN = re.compile(r"\[@eval:\s*([^\]:]+)::([^\]]+)\]")

def _defined_cases(path: pathlib.Path) -> set[str]:
    """Names pytest would actually COLLECT from the file — parsed via AST, never a substring scan.
    A substring match false-greens two real bugs: a case that exists only inside a `# TODO` comment
    (no function), and a misnamed superset (`test_stub_route_and_more` satisfying `test_stub_route`).
    We collect FunctionDef/AsyncFunctionDef names AND any `@pytest.mark.parametrize` ids, then require
    an EXACT match below — so an unbound/misnamed/not-yet-written criterion CANNOT pass the gate."""
    cases: set[str] = set()
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return cases
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cases.add(node.name)                                   # base test function name
            for dec in node.decorator_list:                       # + explicit parametrize ids: foo[id]
                if (isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "parametrize"):
                    for kw in dec.keywords:
                        if kw.arg == "ids" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    cases.add(f"{node.name}[{elt.value}]")
    return cases

# Refund-domain placeholders shipped in gate_eval.py / the Makefile — a build that left ANY of these is a
# half-applied edit that false-REDs (one domain's goal vs another's rubric). The lint owns this mechanically
# so "keep them in sync" stops being prose (HARDENING-LOG iter 6).
_PLACEHOLDERS = ("WHEN asked about refund timing the system SHALL state 5 business days.",
                 "How long do refunds take?")

def _ears_lines() -> list[str]:
    """The criterion PROSE of every EARS line — with the trailing `[@eval: path::case]` token STRIPPED.
    gate_eval.CRITERION is the human/judge rubric and is token-FREE by design (the recipe placeholder
    `WHEN asked about refund timing the system SHALL state 5 business days.` carries no token); the spec
    line that authored it ends with `… [@eval: tests/…::case]`. Comparing a token-free CRITERION against a
    token-BEARING line never matches, false-REDing check 1 on every correct build (HARDENING-LOG iter 7).
    Strip the token so the match is prose-vs-prose, never metadata-vs-prose."""
    out = []
    for f in pathlib.Path("spec/capabilities").glob("*.md"):
        for ln in f.read_text().splitlines():
            if EARS.search(ln):
                out.append(re.sub(r"\s*\[@eval:[^\]]*\]", "", ln).strip(" -"))
    return out

def _gate_eval_sync(ears: list[str]) -> list[str]:
    """Full mode only: gate_eval.CRITERION must be a real EARS line in the spec (not the refund placeholder).
    Catches a Makefile GOAL updated without gate_eval.py, or vice-versa — the mismatch the harness warns
    about 3+ times but never enforced."""
    probs = []
    try:
        from . import gate_eval                                   # the constants under test
    except Exception:                                             # gate_eval not generated yet / import error
        return probs
    crit = getattr(gate_eval, "CRITERION", "").strip()
    if crit in _PLACEHOLDERS:
        probs.append(f"agent/gate_eval.py CRITERION is still the refund placeholder — set it from the P1 EARS line")
    elif crit and crit not in {e.strip() for e in ears}:
        probs.append(f"agent/gate_eval.py CRITERION does not match any EARS line in spec/capabilities/* — Makefile GOAL and gate_eval CRITERION must trace to the SAME P1 line: {crit!r}")
    return probs

def main(preflight: bool = False) -> int:
    problems, seen = [], {}
    for f in pathlib.Path("spec/capabilities").glob("*.md"):
        lines = f.read_text().splitlines()
        for i, ln in enumerate(lines):
            if not EARS.search(ln):
                continue
            window = ln + ("\n" + lines[i + 1] if i + 1 < len(lines) else "")
            m = TOKEN.search(window)
            if not m:
                problems.append(f"{f}:{i+1}  EARS line has no [@eval] token"); continue
            path, case = pathlib.Path(m.group(1).strip()), m.group(2).strip()
            ref = f"{path}::{case}"
            if ref in seen:                          # uniqueness: two EARS lines can't share one case
                problems.append(f"{f}:{i+1}  [@eval] duplicates {seen[ref]}: {ref}")
            seen[ref] = f"{f}:{i+1}"
            if preflight:                            # shape already validated by TOKEN; stop before file I/O
                continue
            if not path.exists():
                problems.append(f"{f}:{i+1}  [@eval] unresolved (no file): {ref}"); continue
            if case not in _defined_cases(path):     # EXACT match — never substring (superset/comment false-green)
                problems.append(f"{f}:{i+1}  [@eval] unresolved (no collectable case `{case}`): {ref}")
    if not preflight:                                # gate mode: the rubric must trace to a real P1 EARS line
        problems += _gate_eval_sync(_ears_lines())
    for p in problems:
        print(f"EVAL-LINT FAIL{' (preflight)' if preflight else ''}: {p}", file=sys.stderr)
    return 1 if problems else 0

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--preflight", action="store_true")
    sys.exit(main(a.parse_args().preflight))
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

# Filled from the spec at build time (one block per capability under test). CRITERION/EVALUATION_STEPS/
# EXPECT_TOOLS come from the SAME P1 EARS line that the Makefile's GOAL/FOLLOWUP are derived from — a
# mismatch (this block = travel, the Makefile GOAL = refund) runs one domain's goal against the other's
# rubric and FALSE-REDs the gate. Override every refund-domain default below per build.
CRITERION = "WHEN asked about refund timing the system SHALL state 5 business days."
EVALUATION_STEPS = ["Does the answer mention refunds?",
                    "Does it state 5 business days?",
                    "Is it free of contradicting timelines?"]
EXPECT_TOOLS = ["search_docs"]
FORBID_TOOLS = []                       # a REAL mutating tool that must not fire ungated (e.g. delete_record).
                                        # NOT `finish` — it emits no execute_tool span, so it'd assert nothing.

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
    # TRAJECTORY is ADVISORY for a 1-capability v1 slice — log its reasons, do NOT gate on them
    # (observability-and-evals.md L95-98/197, SPEC-RECONCILIATION.md decision §D). trajectory_eval flags
    # benign signals on a CORRECT answer — e.g. ANY fail-soft tool span sets attributes["error"] and the
    # graph continues by design, so a single degraded-but-recovered tool call would false-RED a right answer.
    # Outcome (judge-stable) is the v1 hard verdict. Promote trajectory to a blocker (`and ok_t`, mirroring
    # test_demo_gate's `assert ok_t` note) ONLY when a 2nd capability adds a real tool-ordering contract.
    if not ok_t:
        print(f"TRAJECTORY advisory (not blocking until a 2nd capability): {reasons}", file=sys.stderr)
    return 0 if outcome_ok else 1

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
P1's Postgres run reuses the conftest create_all/drop_all-per-test fixture (`patterns/persistence.md` § Tests
use the SAME driver as prod); on a real prod DB use **Alembic migrations**, not auto-`create_all` — that sequence lives in
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
