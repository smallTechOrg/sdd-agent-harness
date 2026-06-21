# Harness Self-Benchmark

The harness's job is to build agents **fast and high-quality**. You cannot improve what you
don't measure, and the dominant cost of a run is not obvious from the inside. This benchmark
makes both axes measurable so every harness change can be proven a win (or caught as a
regression) instead of guessed.

It is the **dogfood loop made quantitative**: the verbose session reports
([SESSION.md](../process/templates/SESSION.md)) supply the raw numbers; this benchmark turns
them into a comparable score row per run.

## What it measures — two axes, never one

A change that makes a run faster but drops quality is a regression, and vice-versa. Every
benchmark run is scored on **both**:

- **Speed** — wall-clock and round-trips (see [rubric.md](rubric.md) → Speed).
- **Quality** — gate-pass, defects, evals, drift (see [rubric.md](rubric.md) → Quality).

A run **passes** only if it clears the quality floor *and* the speed targets. Speed bought by
cutting a quality check does not count.

## How to run

1. Pick a brief from [briefs/](briefs/). Treat it as the user's opening message to `/build`.
2. Run the full build pipeline on it. Use a **fresh checkout / clean tree** so tooling
   cold-start is measured honestly (warm-recipe changes must show up here).
3. The session report captures timestamps (non-negotiable #12) and the Run telemetry table.
4. Score the run against [rubric.md](rubric.md) and append one row to
   [results.md](results.md), noting the harness commit + model/effort so trends are attributable.

Run the **same brief** before and after a harness change to isolate that change's effect. Change
one variable at a time (e.g. warm recipes OR effort drop, not both) so the delta is real.

## Briefs

A small set drawn from the two first-class recipes plus a UI surface — not a large synthetic
suite (same philosophy as `evals/`: a few real shapes beat many fake ones). See
[briefs/](briefs/).

## Files

- [rubric.md](rubric.md) — the two-axis scoring rubric + pass thresholds
- [briefs/](briefs/) — golden briefs (the `/build` inputs)
- [results.md](results.md) — the trend ledger (one row per run)
