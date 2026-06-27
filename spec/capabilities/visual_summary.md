# Capability: Visual Summary (Charts)

> **Phase 2.** Phase 1 ships this as a clearly-labelled non-functional UI stub.

## What It Does
Turns a plain-English request (or a sensible default) into a chart by selecting a chart type and the columns to plot, computing the aggregated series **locally** with pandas, and returning a compact chart specification that the browser renders — raw rows never leave the machine.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string (uuid) | `POST /datasets/{dataset_id}/chart` | yes |
| request | string | Natural-language chart request (e.g. "sales by region"); optional — defaults to an auto-summary | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart_spec | object `{type, x_label, y_label, series: [{label, value}]}` | API response `data.chart_spec`; rendered by the frontend charting component |
| caption | string | API response `data.caption`; one-line plain-English description |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`gemini-2.5-flash`) | One call: given the profile + request, return a chart **plan** (chart type + which column to group by + which to aggregate + aggregation fn) as structured JSON | Fatal for the request: human copy, status `failed` |
| Local pandas | Execute the plan locally (groupby/aggregate) to produce the derived series; only the derived aggregates form the `chart_spec` | Fatal: human copy |

## Business Rules
- **Privacy:** Gemini receives the profile + request and returns only a PLAN (column names + aggregation choice). pandas executes the plan locally; only the **derived aggregated series** (already summary-level, e.g. 12 region totals) is placed in `chart_spec` and sent to the browser. Raw rows never leave the machine and are never in any LLM prompt.
- The plan is validated against the real schema before execution (referenced columns must exist; aggregation must be valid for the dtype). An invalid plan → human copy, no execution.
- Aggregated series are capped (e.g. top-N groups) to keep the chart readable and the payload tiny.

## Success Criteria
- [ ] Requesting "total <numeric> by <category>" returns a bar `chart_spec` whose series matches the local pandas groupby-sum.
- [ ] The chart plan references only columns present in the schema; an out-of-schema column request degrades to human copy, not a crash.
- [ ] No raw row appears in the Gemini prompt or in the `chart_spec` payload (asserted in test).
