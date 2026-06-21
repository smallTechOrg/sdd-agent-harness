# Benchmark Results — trend ledger

One row per run. Run the **same brief** before/after a harness change to attribute the delta.
Change one variable at a time. Times in minutes unless noted. See [rubric.md](rubric.md).

## Runs

| Date | Brief | Harness commit | Model/effort | Brief→FR | →Step0 green | →Delivered | Round-trips | Max parallel | Quality | Verdict | Dominant cost |
|------|-------|----------------|--------------|----------|--------------|------------|-------------|--------------|---------|---------|---------------|
| <!-- 2026-06-22 --> | <!-- B1 --> | <!-- 85ff2b2 --> | <!-- sonnet/max --> | | | | | | <!-- PASS/FAIL+items --> | <!-- PASS/FAIL --> | <!-- tooling/model/rework --> |

## Baseline to capture first

Before optimising anything, run all three briefs once on the **current** harness
(`sonnet / max`, fresh checkout) to set the baseline. The pre-change numbers from the report
that triggered this work — ~10 min brief→FR, ~18 min →Step 0, ~9 sequential iterations — are the
*old* structure; the baseline below measures the **new** one-iteration/parallel-step structure so
later levers (warm recipes, contract-first, critical-path) are measured against it.

## How to read "dominant cost"

The raw columns tell you where to optimise next:
- High **→Step0 green** with low turn count → **tooling** cold-start → warm recipes.
- High **→Delivered** with high turns/tokens → **model latency** → effort/model tiers.
- Quality FAIL or first-pass-review re-bounce → **rework** → contract-first step + critical-path.
