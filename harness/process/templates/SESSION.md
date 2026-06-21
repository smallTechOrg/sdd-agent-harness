# Session Report — YYYY-MM-DD — [branch]

**Started:** YYYY-MM-DD HH:MM  
**Branch:** feature/...  
**FR/CR:** FR-NNN — [title]

> **This report is a live tail, not a retrospective.** Write to it continuously — every ~2
> minutes during active work. A reader watching this file should be able to see what is
> happening right now without asking. The Latency Ledger is the primary artifact; every other
> section feeds off it. Over-record: dead-ends, retries, and friction are the signal.

---

## API Keys

| Key | Present |
|-----|---------|
| <!-- e.g. OPENAI_API_KEY --> | yes / no |

---

## FR reference

> Step Plan + Progress Tracker live in the FR — the coordination hub all agents read and write.
> **FR:** `spec/features/FR-NNN.md`

---

## Latency Ledger

> **Write a row the moment a stage/step starts — not at the end.** This is the live tail.
> Fill Start immediately; fill End + Dur + Dominant cost on handoff. A row that stays blank
> while work is happening means the log is behind — catch up now, not at the end of the run.
> A run with empty or end-filled rows is non-compliant (#12) and the analyser flags it.
>
> **Every ~2 minutes** during a long sub-task (uv sync, npm install, multi-file write, test run
> >30s) append a one-line note in the `Notes` column: `HH:MM:SS running uv sync…`. This is the
> only place timestamps go outside stage Start/End — nowhere else in this file, and never in
> src/ or docs.

| # | Stage / Step | Start | End | Dur | Model | Dominant cost | Notes (live, ~2 min) |
|---|-------------|-------|-----|-----|-------|---------------|----------------------|
| — | session open | HH:MM:SS | | | | | |
| 0 | scaffold | | | | sonnet/low | | |
| 1 | <!-- step --> | | | | | | |

**Parallel front achieved:** <!-- max steps in flight; if 1, the swarm collapsed to a queue -->  
**Critical path:** <!-- longest dependency chain + its total time -->  
**Biggest cost to halve:** <!-- the one row that, if halved, helps most -->

> Dominant cost codes: `model-latency` · `tooling/network` · `rework/retry` · `waiting-on-user` · `idle`

---

## Progress Tracker

> Everyone updates their row on handoff. Status: `todo → in-progress → gate-green → accepted`.
> `accepted` only when the user accepts the whole at the iteration boundary.

| Step | Status | Gate result | Reviewer | Dominant cost |
|------|--------|-------------|----------|---------------|
| 0 | todo | — | — | — |

---

<!-- ── Each stage appends a section below. FIRST tool call = append Start: to ledger. ── -->

## [Stage / Step N] — [Agent]

**Start:** HH:MM:SS  ← write this FIRST, before any other tool call  
**End:** HH:MM:SS  
**Model / effort:** sonnet / medium  
**Ran ∥ with:** <!-- step 2, 3 — or "—" -->

### Decisions
<!-- What and why — include alternatives rejected. -->
-

### Trace
<!-- Replay narrative: steps in order, retries + why, dead-ends, commands run. -->
-

### Harness friction
<!-- [blocker|slow|papercut] + harness file if known. "Nothing" only if genuinely zero. -->
- [papercut] <!--  -->

### Gate result
```
$ <command>
<output>
```
**Result:** ✓ pass / ✗ fail

### Blockers / open questions
-

### What is next
<!-- One sentence. -->

---

<!-- ── End-of-session rollup — written once when the iteration closes. ── -->

## Harness Feedback — dogfood rollup

> Concrete harness-improvement candidates mined from every Harness friction entry above.

| Friction | Severity | Stage | File to change | Proposed fix |
|----------|----------|-------|----------------|--------------|
| <!-- --> | slow | | | |

## Run telemetry — rubric rollup

> Derive from the Latency Ledger above. Do not reconstruct from memory.

| Metric | Value | Target |
|--------|-------|--------|
| Brief → FR approved | | ≤ 3 min |
| FR approved → Step 0 green | | ≤ 5 min |
| Brief → iteration delivered | | ≤ 30 min |
| Human round-trips | | ≤ 2 |
| Parallel-step front (max in flight) | | ≥ 3 |
| Slowest single stage | | (trend) |
| Critical-path length | | (trend) |
