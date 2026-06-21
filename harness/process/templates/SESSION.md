# Session Report — YYYY-MM-DD — [branch]

**Started:** YYYY-MM-DD HH:MM  
**Branch:** feature/...  
**FR/CR:** FR-NNN — [title]  
**Iteration:** [the requirement being delivered]  •  **Current step:** Step N — [goal]

> **This report is dogfood data.** Write it verbose enough that someone improving the *harness*
> (not the product) can replay this run from it. Capture the path NOT taken: every retry, every
> dead-end, every place the canon was ambiguous/missing/wrong, every human correction, and the
> wall-clock cost of each. A clean happy-path log teaches the harness nothing. When in doubt,
> over-record — friction is the signal. Anything that slowed you down goes in **Harness Friction**.

---

## API Keys

| Key | Present |
|-----|---------|
| <!-- e.g. OPENAI_API_KEY --> | yes / no |

---

## Step Plan (one iteration → parallel steps)

> The whole requirement ships in one iteration; these are its steps (the FR holds the DAG).

| Step | Goal | Depends on | Gate command | Status |
|------|------|-----------|-------------|--------|
| 0 | Scaffold — /health green | — | `curl http://localhost:8001/health` | pending |
| 1 | First model + data layer | 0 | `uv run pytest tests/unit/` | pending |
| 2 | Core loop (stubbed) | 0 | `uv run pytest` | pending |
| ... | | | | |

---

<!-- Each agent appends a new section using the format below. -->
<!-- Stamp start/end from the host clock: `date '+%Y-%m-%d %H:%M:%S'` (non-negotiable #12). -->
<!-- ────────────────────────────────────────────────────────── -->

## [Stage] — [Agent name]

**Start:** YYYY-MM-DD HH:MM:SS  
**End:** YYYY-MM-DD HH:MM:SS  
**Duration:** Nm Ns  
**Model / effort:** <!-- sonnet / medium -->  
**Ran parallel with:** <!-- step 2, step 3 — or "—" if serial -->  
**Dominant cost:** <!-- model-latency | tooling/network | rework/retry | waiting-on-user | waiting-on-background — the ONE thing that ate the most wall-clock here -->  
**Tool calls:** <!-- N -->  •  **Retries:** <!-- N (and why, in Trace) -->

### Decisions
<!-- What was decided and why — AND the alternatives rejected. One bullet per decision. -->
-

### Trace — what actually happened
<!-- The narrative a harness-improver replays: steps taken in order, retries and WHY each was
     needed, dead-ends and what was learned, commands run. Include false starts, not just the
     path that worked. Note token/turn cost if notable. -->
-

### Harness friction — dogfood signals
<!-- The point of this report. For each: what in harness/ helped, hindered, was ambiguous,
     missing, or wrong. Tag severity [blocker|slow|papercut] and name the file if known.
     "Nothing" is a valid entry only if you genuinely hit zero friction. -->
- [papercut] <!-- e.g. recipe selection table in planner.md didn't cover X — guessed -->

### Gate result
```
$ <command run>          # stamped: YYYY-MM-DD HH:MM:SS
<output>
```
**Result:** ✓ pass / ✗ fail <!-- on fail, paste the real error, not just "failed" -->

### Blockers / open questions
<!-- Anything unresolved that the next agent or human must address. -->
-

### What is next
<!-- One sentence: what the next agent or step should do. -->

---

<!-- ────────────────────────────────────────────────────────── -->
<!-- Written once at end of session — the dogfood payload. -->

## Harness Feedback — dogfood rollup

> Roll up every **Harness friction** bullet above into concrete harness-improvement candidates.
> This is what we mine to improve `harness/` itself. Order by cost paid.

| Friction | Severity | Stage | Harness file to change | Proposed fix |
|----------|----------|-------|------------------------|--------------|
| <!-- e.g. intake asked 2 serial rounds --> | slow | researcher | researcher.md | <!-- draft-first --> |

## Latency ledger — where the wall-clock actually went

> **The primary speed-diagnosis artifact.** One row per stage/step **in execution order**, filled
> *as you go* (not reconstructed at the end). This is what tells a harness-improver how to make the
> next run faster: it exposes the **critical path** (the longest dependency chain — the only thing
> whose reduction shortens the run) and the **dominant cost** of each unit (so we optimise the real
> bottleneck — model latency vs tooling vs rework vs idle — not a guessed one). A run with this
> table empty or undated is **non-compliant** (#12) and the analyser flags it.

| # | Stage/Step | Start | End | Dur | Model/effort | Ran ∥ with | Dominant cost | Tool calls | Retries |
|---|-----------|-------|-----|-----|--------------|-----------|---------------|-----------|---------|
| 0 | scaffold  | <!--HH:MM:SS--> | | | | — | tooling/network | | |
| 1 | <!--model--> | | | | | <!--2,3--> | | | |
| … | | | | | | | | | |

**Parallel front actually achieved:** <!-- max steps in flight at once — compare to the plan's parallel groups; if 1, the swarm collapsed to a queue (the baseline failure) -->  
**Critical path:** <!-- the step chain that set total time, and its length Nm -->  
**Biggest single cost:** <!-- the one stage/cost that, if halved, helps most -->

## Run telemetry — rubric rollup (derive from the ledger)

> The [benchmark rubric](../../benchmark/rubric.md) metrics, computed from the ledger above.

| Metric | Value | Rubric target |
|--------|-------|---------------|
| Model / effort | <!-- e.g. sonnet / medium --> | cheapest tier that clears the bar |
| Wall-clock: brief → FR approved | <!-- Nm --> | ≤ 3 min |
| Wall-clock: FR approved → Step 0 green | <!-- Nm --> | ≤ 5 min |
| Wall-clock: brief → iteration delivered | <!-- Nm --> | ≤ 30 min |
| Human round-trips | <!-- N --> | ≤ 2 |
| Parallel-step front (max in flight) | <!-- N --> | ≥ 3 |
| Slowest single stage | <!-- stage — Nm --> | (trend) |
| Critical-path length | <!-- Nm --> | (trend) |

---
