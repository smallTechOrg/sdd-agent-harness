# Capability: Visualize the answer

## What & why
When a trend, comparison, or distribution is communicated better as a picture — or the user explicitly asks
for a chart — the agent produces a valid **Vega-Lite** spec backed by a read-only query, which the UI
renders as an interactive chart. Realizes the "get visualizations and charts" success criterion in
`spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN the user asks for a chart/visualization (or the answer is a trend/comparison best shown visually) the system SHALL produce a valid Vega-Lite spec backed by a read-only SQL query and render it in the UI.
- WHEN it creates a chart the system SHALL choose a mark and encodings appropriate to the question (e.g. line for trend over time, bar for category comparison).
- IF the requested chart needs a field not present in the dataset THEN the system SHALL explain what is missing instead of fabricating data.

## Tools & layers touched
- tool: `create_chart`  (in-process @tool — runs the chart's read-only SQL, embeds the rows as `data.values` in a validated Vega-Lite v5 spec, persists a `charts` row tied to the run; `harness/patterns/tools-and-mcp.md`)
- tool: `get_schema`, `run_sql`  (as in `query-data`)
- layers: guardrails (action-safety) ON — the chart's SQL goes through the same read-only path

## Evaluation
- outcome evaluation_steps:  # LLM-judge scores the final answer + chart 0–5
  - Did the agent produce a Vega-Lite spec that is valid JSON with a `mark` and an `encoding`?
  - Is the chart's data backed by a query over the dataset (not fabricated values)?
  - Is the chart type appropriate to the question (trend→line, comparison→bar, etc.)?
- expect_tools: [create_chart]
- forbid_tools: []

## Notes
- `create_chart` validates the spec server-side (well-formed JSON, has `mark` + `encoding`) and **fails
  soft** — on an invalid spec it returns an error string the model can correct, never raising.
- The chart spec (with embedded data) is persisted in `charts` and returned in the `POST /runs` envelope so
  the UI renders it with `vega-embed`; the `/traces` viewer shows the `create_chart` tool span. The UI does
  not re-implement charting logic — it renders the spec the agent produced.
- Part of the v1 feature set (built together with query + multi-turn, not deferred).
