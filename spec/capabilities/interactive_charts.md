# Capability: Interactive Charts

## What It Does
Renders an interactive chart (zoom/hover/filter) alongside the result table when the answer lends itself to visualisation, driven by the locally-computed aggregate. (Phase 3)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| result schema | JSON | `synthesize_answer` (bounded result) | yes |
| bounded aggregate data | JSON | `analysis_steps` / result table | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart_spec | JSON (type + encodings) | `questions.chart_spec_json`; UI ChartView |
| chart data | JSON (bounded aggregate) | UI ChartView |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini Flash | choose chart type + encodings from result schema (no full rows) | chart omitted; table still shown |

## Business Rules
- The chart's data is the **locally-computed bounded aggregate**, never full data rows.
- A chart is only proposed when the result shape supports one; otherwise table-only.

## Success Criteria
- [ ] For a "metric by category/time" answer, an interactive chart renders with hover values and zoom/filter.
- [ ] The chart data matches the result table (same locally-computed aggregate).
