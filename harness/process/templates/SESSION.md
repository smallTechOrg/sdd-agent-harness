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

## Run telemetry

> The numbers that make latency regressions visible run-over-run.

| Metric | Value |
|--------|-------|
| Model / effort | <!-- e.g. sonnet / max --> |
| Wall-clock: brief → FR approved | <!-- Nm --> |
| Wall-clock: approval → iteration 0 green | <!-- Nm --> |
| Wall-clock: total | <!-- Nm --> |
| Human round-trips | <!-- N --> |
| Slowest single stage | <!-- stage — Nm --> |

---
