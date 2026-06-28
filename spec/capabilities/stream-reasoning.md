# Capability: Stream Live Reasoning Steps

## What It Does
Streams the agent's reasoning to the browser as it works — each step (plan / write code / run / inspect / refine) with its status (tried / failed / worked) and a live `Step N of M` counter — so the user sees the plan before execution and watches the loop progress in real time.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run events | step objects | LangGraph streaming runner | yes |
| max_steps | int | agent state | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| SSE `step` events | event stream | live step viewer |
| RunStep records | rows | SQLite `run_steps` (replayable audit) |
| `run_started` / `answer` / `done` / `error` events | event stream | frontend |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| (internal) streaming runner | yield per-node step events | client disconnect → run continues server-side and is persisted |

## Business Rules
- Emit one `step` event per node execution, in order, before the final `answer`.
- The plan is streamed before any code executes.
- Every streamed step is also persisted to `run_steps` so history can replay it.
- Step events carry only schema/code/aggregate summaries — never raw rows.

## Success Criteria
- [ ] The user sees steps arrive incrementally (not all at once at the end) with an advancing `Step N of M` counter.
- [ ] Each step shows its node and tried/failed/worked status.
- [ ] After a run, the same step sequence is retrievable from `run_steps` via `GET /runs/{id}`.
