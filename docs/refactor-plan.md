# Refactor Plan — toward the leader in spec-driven development

> **Lean by design.** If this plan needs more than a skim, it's wrong (the v3 lesson). The full field
> survey + sourcing live in [`sdd-deck.md`](sdd-deck.md). Revised after a 3-lens adversarial critique.

## Goal & moat
**End goal:** the leader in SDD — works on Claude Code, builds a **complete agentic AI stack**, iterative,
scoped, a pleasure to develop on.
**The moat (only we have it):** we **boot the built agent and judge whether the answer is right** — a `200`
with a wrong answer FAILS. Competitors assert structure or read code; none execute-and-judge.
**Hard truth:** that gate is **not in the working tree — it lives in git history at `befd889`.** So step one
is *recovering* it, not "re-homing" it.

## What must not regress (the proven bar — currently only in git history)
1. **proof-it-ran gate** — boot + two-turn HTTP + **multi-sampled judge-stable** outcome eval; wrong answer fails.
   (`befd889:harness/workflows/gates.md`, `eval_lint.py`, `gate_eval.py`, `scripts/demo_gate.sh`)
2. **EARS + `[@eval]`** AST-collectable test-binding (not substring).
3. **agentic-trajectory checks** — tool spans, `force_finalize`, a guardrail that *fires*, multi-turn.
4. **thin-slice** — one real capability + honest stubs.
Known-good app to re-prove against: **`d6def4a`** (data-analysis, "40 files, gate exits 0").

## The model
- `harness/` = agent-agnostic details (rules + recipes + gate scripts). `spec/` + `code/` generated.
  `.claude/` = thin index into `harness/`.
- **Code is the source of truth; the spec is kept reconciled to it, mechanically.** Reconciliation is the
  invariant; on conflict **code wins** and the spec re-projects. `spec → code` only at bootstrap / change
  proposal, where **the acceptance oracle is fixed from your intent in plan-mode BEFORE code is written** (so
  the gate never grades the code's own author).

## Reconciliation = a *coverage* gate (honest naming) + the execution moat on top
Deterministic **coverage** gate (table-stakes — OpenSpec/Spec Kit have it; not the moat):
- every `[@eval]` resolves to a real AST-collectable test **that re-runs and passes** (not just "files touched together");
- every capability's `targets:` glob matches ≥1 file and **not** the whole tree; flag code outside all globs;
- edge cases are explicit: **rename/delete** (a glob matching nothing → FAIL), **honest stub** (marked, reconciles, ≠ phantom), **multi-file** (dir-scoped globs);
- `targets:` coverage is a **warning until v1 is green**, then fail-closed (churny early layouts thrash globs).
The **moat is execution-and-judge** (the proof-gate), layered above. "Does code semantically contradict the
spec" is **LLM-judged and advisory** — never claimed as deterministic.

## The agentic stack (the end goal, not just plumbing)
Apps we build need the full stack: control loop · tools · memory · retrieval · multi-agent · observability/traces
· evals · guardrails. These live as **recipes in `harness/recipes/`**, salvaged from `befd889:harness/patterns/`
(the 11 layers), **re-pinned to current verified versions**, paged in on demand, each under a per-file size cap.
A recipe is **populated and proven by one real corpus app** — resolving "simulate vs build": we simulate for
breadth, but **one real keyed app** exercises the stack and the moat.

## Leanness, enforced (the v3 antidote)
A **fail-closed line budget from Phase 1**: `harness/` total ≤ a hard ceiling + a per-file screen cap, checked
in the pre-commit hook. A brick that can't fit the budget is wrong. Leanness is the one invariant v3 violated —
so it gets a gate like every other invariant, not a vibe check at the end.

## Phases (each ends GREEN and real-execution-anchored; revert the brick if red)
1. **Recover the moat.** Extract the `befd889` gate into `harness/gates/`; prove it exits 0 on `d6def4a`; pin
   each hard-won false-green fix (asyncio_mode, AST-not-substring, empty-data, UI real-value assert, two-turn)
   as a named regression. Add the mechanical **leanness budget** to pre-commit. *Exit: the real gate runs green
   in the new tree; budget enforced.*
2. **Skeleton & spec format.** `harness/ spec/ code/`; constitution folded into `harness.md`; spec = EARS +
   `[@eval]` + `targets:`. **One golden app** (spec+code+eval) the recovered gate can run. *Exit: coverage gate
   green; one keyed proof-gate run green **and** an injected wrong answer FAILS.*
3. **Coverage gate.** Build the deterministic gate (binding + glob coverage + re-run + edge cases). *Exit: pass
   on a reconciled pair; fail on each broken case (no test / empty glob / orphan code).*
4. **The workflow.** `/new`, `/change`, `/sync` as `harness/` procedures: plan-mode intake **fixes the oracle**
   → generate code → spec re-projects → coverage gate → proof-gate → review (code-truth, one-way). *Exit:
   dry-run `/change` on a scripted intent yields a reconciled, gated change; the keyed golden app stays green.*
5. **Agentic recipes.** Salvage the core layers (loop, tools, observability, evals) from `befd889`, re-pinned;
   the golden app uses them; the gate's **trajectory** checks pass. *Exit: app boots; agentic checks green.*
6. **`.claude` index + DX.** Thin `.claude/` stubs; a one-line **CI grep** asserts each names an existing
   `harness/` doc (no generator yet — add only when a 2nd agent adapter exists). Self-diagnosing errors +
   one-command dev as per-brick acceptance criteria. *Exit: comprehension test (read it all in ~30 min) + DX review.*

## Validation
Simulate workflows (cheap, mostly mechanical) for breadth **+ one real keyed end-to-end run** of the golden app
per merge: boots, two turns, judge-stable eval passes, **and an injected wrong answer FAILS**. The **inner loop
stays deterministic** (FakeModel / mechanical) — never a live single-sample judge (that re-imports the v3
false-green). Full judge-stability only at the merge gate.

## Migration & rollback
- From today's disk (thin `.claude/`, no `harness/`, `examples/calc-agent` present): Phases 1-2 create
  `harness/`; the existing one-way `.claude/` artifacts are **kept** (they already match code-truth) and
  re-pointed at `harness/` in Phase 6; `calc-agent` stays as a teaching example / candidate fixture.
- **Per-phase rollback:** if a phase's exit checkpoint is red, revert that brick — never accumulate on red.

## Forks to confirm (defaults chosen — NOT a blocking questionnaire; raised when each bites)
1. **Truth model (the big one):** *code-is-truth + enforced reconciliation* (planned — lean, matches your "code
   is the source of truth") **vs** *symmetric co-generation* (heavier; needs conflict-authority machinery). **Confirm.**
2. **Change record:** git branch + PR body (default) vs a `changes/<slug>.md` delta.
3. **Gate enforcement point:** pre-commit (default) vs inside `/change` only; define the WIP escape.
Everything else defaults to *less* and is decided at the brick that needs it.

---
*Provenance lives in [`sdd-deck.md`](sdd-deck.md). "Planned"/"default" = my recommendation; yours to override brick-by-brick.*
