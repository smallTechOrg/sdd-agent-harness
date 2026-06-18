# Pattern: Observability & Evals

**Canonical home for layer 9 (Observability + evals)**
([`../agentic-architecture.md`](../agentic-architecture.md)). How you see what the agent did and prove
its answers are good. Other docs (`react-agent.md`, `phases.md`) link here for the details.

---

## Observability — three signals

1. **Structured logs** — every node emits a JSON log bound to `run_id` (and `thread_id` for multi-turn).
   No bare `print`; one structured event per node with the action's `description`.
2. **Usage** — every LLM call records input/output tokens + estimated cost, accumulated on the run.
   Sub-agent usage rolls up to the parent run ([`multi-agent.md`](multi-agent.md)). Token/cost per run
   must never be invisible.
3. **Traces (baseline)** — spans following the **OpenTelemetry GenAI semantic conventions** (one span
   per LLM call, tool call, retrieval), exported to a tracing backend (LangSmith / Langfuse / OTLP —
   pick from [`../tech-stack.md`](../tech-stack.md) § Agentic Stack Tech). A trace shows the whole
   reason → act → observe path for one run. OTel tracing ships in **Phase 1**, not as an add-on;
   aggregate metrics + latency dashboards are what earn their place later.

The user-facing reasoning trace (`action_history` with plain-English `description`s) is a **product**
surface, not just an ops one — see [`react-agent.md`](react-agent.md) § State. Glass box, never a
spinner over a black box.

## Evals — plumbing tests aren't quality tests

A run can pass every layer (200, valid schema, no crash) and still return a **wrong answer**. Evals
catch that. Keep them small, fixed, and version-controlled.

- **Eval set** — a handful of representative `input → expected` (or rubric/property) cases.
  - **Rubric/property checks** are the default — outputs vary run to run because the model is real, so
    assert on structure, presence, and properties, not exact strings.
  - **LLM-as-judge** (rubric scoring) where outputs are open-ended — judge with a capable model
    (Opus 4.8) against an explicit rubric.
  - Component evals: retrieval recall@k ([`retrieval.md`](retrieval.md)), tool-selection accuracy.
- **Always real** — evals run against the **real model** (key from a CI secret), in CI on every run.
  There is no stub mode. Loose assertions absorb output variance while still catching answer-quality
  drift and plumbing regressions.
- **Regression gate** — the richer eval suite + a threshold that fails the build earns its place at
  Phase 7; the Phase 1 skeleton is one tiny dataset + ≥1 loose assertion. This is what makes
  prompt/model changes safe to ship.

## Phasing

Baseline (Phase 1) — structured per-`run_id` logs + token/cost on the run + **OTel GenAI trace export**
+ an **eval-harness skeleton** (one tiny dataset, ≥1 loose assertion, runs against the real model in CI),
all gate items. Aggregate metrics/latency dashboards + a richer eval suite (LLM-judge, component evals) +
the regression threshold earn their place at Phase 7. Authority: [`../phases.md`](../phases.md) §
Agentic layers by phase.

## Don't log secrets

Usage and traces must never carry secret values — presence-only, per
[`../secret-hygiene.md`](../secret-hygiene.md).
