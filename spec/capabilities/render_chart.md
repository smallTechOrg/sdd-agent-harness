# Capability: Render Chart

> **Status: DEFERRED — Phase 2.** Phase 1 ships a labelled "Coming soon" chart area.

## What It Does
Chooses an appropriate chart type from the shape of an answer's result set and returns a chart spec the frontend renders client-side.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| result | list[dict] | `analyze_question` result rows | yes |
| question | str | the run's question | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart | dict (spec: type, x, y, series) | API `data.chart`; UI chart area |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| (none / optional Gemini for type hint) | choose chart type from result shape | fall back to a table-only answer (chart `null`) |

## Business Rules
- Chart spec is derived from the aggregate result only — no raw rows.
- If the result is not chartable (single scalar, too many series), return `chart: null` and rely on the answer + table.

## Success Criteria
- [ ] A grouped aggregate result yields a bar/line chart spec the UI renders.
- [ ] A single-scalar result yields `chart: null` with no error.
