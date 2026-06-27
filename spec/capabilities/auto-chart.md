# Capability: Auto-Chart

## What It Does
When a question is comparative or trend-shaped, the agent automatically chooses an appropriate chart type (bar / line / pie) and returns a chart spec the UI renders inline — without the user picking a chart type.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| aggregate_table | small result table | `run_local_aggregation` | yes |
| intent | enum (comparison/trend/distribution/single_value) | `plan_aggregation` output | yes |
| question | string | user | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart | ChartSpec `{type,title,labels,series}` or `null` | API response → inline Recharts render |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`compose_answer_and_pick_chart`) | choose chart type + build spec from the aggregate table | Phase 1: error; Phase 5: degrade to `chart=null` (answer only) |

## Business Rules
- Chart selection rule of thumb: comparison → `bar`, trend over ordered/time axis → `line`, share/distribution → `pie`, single value → no chart (`null`).
- The chart spec is built **only from the aggregate table** — no raw rows.
- `labels.length` equals each series' `values.length`; pie uses exactly one series. (Shape per [api.md → Chart Spec](../api.md#chart-spec).)
- The user does not choose the chart type in Phase 1 (manual toggle is a labelled stub).

## Success Criteria
- [ ] A "by region" comparison question yields a `bar` chart with one label per region and matching values.
- [ ] A "over time / by month" question yields a `line` chart ordered by the time axis.
- [ ] A single-value question (e.g. "what's the total revenue?") returns `chart: null` and only a text answer.
- [ ] The rendered chart values match the locally-computed aggregate exactly.
