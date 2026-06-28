# Agent Graph

> The concrete LangGraph composition for this project. Patterns are drawn from `harness/patterns/agentic-ai.md`: **Planning (#6)**, **LLM-Generated Code Execution (#22)**, **Tool Use (#5)**, with **Resource-Aware Optimization (#16)** as the step-cap cost guard, **Exception Handling (#12)**, and **Goal Setting & Monitoring (#11)** for the stopping condition. Memory (#8) is added in Phase 4. This is a **plan-then-execute** graph — above the base ReAct loop because the plan is drafted explicitly up front and execution is a capped, replannable loop of locally-run generated code.

Replaces the skeleton's `transform_text` slot. The graph object exported as `agentic_ai` from `src/graph/agent.py` stays the entry point; `src/graph/runner.py` keeps the create-row → invoke → finalize shape but is extended for datasets, steps, and cost.

---

## State

`src/graph/state.py` — `AgentState(TypedDict, total=False)`:

| Field | Type | Set by | Meaning |
|-------|------|--------|---------|
| `run_id` / `question_id` | `str` | runner | the `questions` row id |
| `dataset_id` | `str` | runner | dataset under analysis |
| `csv_path` | `str` | runner | local file path (engine reads this) |
| `schema` | `list[dict]` | runner | `[{name, type}, ...]` — sent to LLM |
| `sample_rows` | `list[dict]` | runner | ≤ `AGENT_SAMPLE_ROWS` rows — sent to LLM |
| `question_text` | `str` | runner | the user's plain-language question |
| `messages` | `list` | runner (P4) | prior conversation turns (memory) |
| `plan` | `list[str]` | `plan` | ordered analysis steps (text) |
| `steps` | `list[dict]` | `execute_step` | `[{index, code, language, result, error}]` — bounded results only |
| `step_count` | `int` | `execute_step` | iterations taken (cost guard) |
| `next_code` | `str \| None` | `plan`/`replan` | code for the next step to run |
| `plan_complete` | `bool` | `execute_step`/`replan` | all plan steps done |
| `cost_guard_warning` | `str \| None` | `step_cap_check` | set when the cap is hit |
| `tokens_in` / `tokens_out` | `int` | every LLM node | accumulated usage |
| `answer` | `str` | `synthesize_answer` | plain-language answer |
| `key_numbers` | `list[dict]` | `synthesize_answer` | `[{label, value}]` |
| `result_table` | `dict` | `synthesize_answer` | `{columns, rows}` (bounded) |
| `chart_spec` | `dict \| None` | `synthesize_answer` (P3) | chart type + encodings |
| `followups` | `list[str]` | `suggest_followups` (P2) | 2–3 follow-up questions |
| `error` | `str \| None` | any node | error message |
| `status` | `str` | finalize/handle_error | `completed` \| `failed` |

**Privacy invariant:** only `schema`, `sample_rows`, prior `steps[].result` (bounded aggregates), `question_text`, and `messages` are ever placed into an LLM prompt. No node ever reads the full CSV into a prompt.

## Nodes

| Node | Pattern | LLM? | Responsibility |
|------|---------|------|----------------|
| `plan` | Planning #6 | yes | From schema + sample_rows + question, produce an ordered `plan` (≤ `AGENT_MAX_STEPS` steps) and the `next_code` for step 1 (SQL preferred, pandas when needed). Record tokens. |
| `execute_step` | Code Execution #22 / Tool Use #5 | no | Run `next_code` via the local analysis engine over the FULL dataset; append `{code, result, error}` to `steps` (result bounded to `AGENT_MAX_RESULT_ROWS`); increment `step_count`. On code error, store the error so `replan` can react. |
| `replan` | Planning #6 | yes | Given the plan and the bounded results/errors so far, decide if more steps are needed; if so emit the `next_code` for the next step; else set `plan_complete=True`. Record tokens. (Phase 1: minimal — single-step plans set `plan_complete` immediately and skip replanning; the node exists and is wired.) |
| `synthesize_answer` | — | yes | From the bounded step results, write `answer` + `key_numbers` + `result_table` (P3: + `chart_spec`). Record tokens. |
| `suggest_followups` | — | yes | (Phase 2) one cheap call → 2–3 `followups`. |
| `handle_error` | Exception #12 | no | Set `status=failed`, keep `error`. |
| `finalize` | — | no | Set `status=completed`. |

## Edges

```
entry → plan
plan ──(error?)──────────────► handle_error
plan ──(ok)──────────────────► execute_step
execute_step ─────────────────► step_cap_check        (conditional router)
step_cap_check ──(plan_complete OR step_count ≥ MAX_STEPS)──► synthesize_answer
step_cap_check ──(more steps AND under cap)─────────────────► replan
replan ──(error?)─────────────► handle_error
replan ──(next_code set)──────► execute_step           (loop)
replan ──(plan_complete)──────► synthesize_answer
synthesize_answer ────────────► suggest_followups       (P2; P1: → finalize)
suggest_followups ────────────► finalize
synthesize_answer ──(error?)──► handle_error
finalize → END
handle_error → END
```

`step_cap_check` is a conditional-edge function (`src/graph/edges.py`): if `state["step_count"] >= MAX_STEPS` and not `plan_complete`, it sets `cost_guard_warning` and routes to `synthesize_answer`; if `plan_complete`, routes to `synthesize_answer`; otherwise routes to `replan`.

## Cost Guard (Resource-Aware Optimization #16)

- `AGENT_MAX_STEPS` (default 5) caps `execute_step` iterations.
- The router enforces the cap; on hit, `cost_guard_warning` is set and the agent synthesises a best-effort answer — it never loops freely.
- Flash-tier model is the default; token usage accumulated in `tokens_in`/`tokens_out` and converted to USD in the runner (see [`architecture.md`](architecture.md#cost-accounting)).

## Concurrency

Per question the graph runs **sequentially** (each step's bounded result feeds the next). There is no in-graph parallel fan-out in Phase 1 — DuckDB handles intra-step parallelism natively. Multiple questions are independent and may run concurrently at the API layer (separate runner invocations, separate DB rows).

## Error Handler & Finalize

- Any node sets `error` on exception; the conditional edges route to `handle_error`, which sets `status=failed` and preserves the message for the API/UI. The graph never crashes the request.
- `finalize` sets `status=completed`. The runner then writes the `answer`, `analysis_steps` (code+result), and `cost_records` rows.
- Resilience hardening (retries/timeouts on the Gemini call, DuckDB error → replan-with-error) is layered in the Phase 4 / resilience pass; the skeleton's try/except in each node is the Phase 1 floor.

## Observability

`src/observability/events.py` (structlog) emits a structured event at: question received, plan produced (with token usage), each `execute_step` (code hash + result row count + latency — never full data), cap hit, answer synthesised, and error. One line per run minimum, confirmed in the Phase 1 gate.

## Graph Assembly (pseudocode — `src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.nodes import (
    plan, execute_step, replan, synthesize_answer,
    suggest_followups, handle_error, finalize,
)
from graph.edges import after_plan, step_cap_check, after_replan, after_synthesize

def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("execute_step", execute_step)
    g.add_node("replan", replan)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_node("suggest_followups", suggest_followups)   # P2; P1 passthrough → finalize
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("plan")
    g.add_conditional_edges("plan", after_plan,
        {"execute_step": "execute_step", "handle_error": "handle_error"})
    g.add_conditional_edges("execute_step", step_cap_check,
        {"replan": "replan", "synthesize_answer": "synthesize_answer"})
    g.add_conditional_edges("replan", after_replan,
        {"execute_step": "execute_step",
         "synthesize_answer": "synthesize_answer",
         "handle_error": "handle_error"})
    g.add_conditional_edges("synthesize_answer", after_synthesize,
        {"suggest_followups": "suggest_followups", "handle_error": "handle_error"})
    g.add_edge("suggest_followups", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()
```

> **Phase 1 scope of this graph:** all nodes and edges are wired and compile. `plan` may produce a single-step plan and `replan` immediately sets `plan_complete` (minimal but real), so a typical Phase 1 question runs `plan → execute_step → step_cap_check → synthesize_answer → (suggest_followups passthrough) → finalize`. Multi-step replanning, follow-ups, and chart specs become real in Phases 2–3; multi-file file-selection in the plan node is Phase 4.
