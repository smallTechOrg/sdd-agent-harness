# Capability: Visualisation

## What & why

When a user's question is naturally answered with a chart — "Show me sales by month as a bar chart", "Plot the distribution of ages", "Compare revenue across regions" — the agent calls `generate_chart_spec` after `execute_sql` to produce a Plotly/Vega-Lite JSON specification. The spec is embedded in the `finish` answer and rendered as an interactive chart in the web UI without a round-trip to an external service. Statistical insight questions ("What's the correlation between X and Y?", "Are there outliers in this column?") return a prose interpretation of the computed statistics alongside an optional supporting chart. This capability serves the second success criterion in `spec/product.md`: a valid chart spec is returned and renders without errors in the UI.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user explicitly requests a chart or the agent judges that a visual encoding would substantially aid understanding the system SHALL call `execute_sql` to obtain the data, then call `generate_chart_spec` with the query results and a chart type, and embed the resulting JSON spec in the `finish` answer.
- WHEN `generate_chart_spec` is called the system SHALL return a JSON object that is a valid Plotly figure spec (with at minimum a `data` array and a `layout` object) or a valid Vega-Lite single-view spec (with at minimum `$schema`, `data`, `mark`, and `encoding` fields).
- WHEN the user asks for a specific chart type (bar, line, scatter, pie, histogram) the system SHALL honour that type in the generated spec rather than substituting a different type.
- WHEN the query result has only one row or one distinct value the system SHALL return a prose answer and explain that a chart would not add information, rather than generating a degenerate or empty chart.
- IF `execute_sql` returns an error or empty result set THEN the system SHALL NOT call `generate_chart_spec` and SHALL report the data issue in prose instead.
- WHEN the user asks a statistical question (distribution, correlation, outliers, summary statistics) the system SHALL compute the relevant aggregation via `execute_sql` and return a prose interpretation of the numbers, supplemented by a chart spec where a visual makes the finding clearer.

## Tools & layers touched

- tool: `get_dataset_schema` (in-process @tool — confirm numeric/categorical column types before choosing chart axes)
- tool: `execute_sql` (in-process @tool — retrieve the data to visualise)
- tool: `generate_chart_spec` (in-process @tool — produce a Plotly or Vega-Lite JSON spec from query results and chart parameters)
- tool: `finish` (in-process @tool — emit the prose answer with the chart spec embedded as a JSON field)

## Evaluation

- outcome evaluation_steps:
  - Does the answer include a chart spec (a JSON object with the required Plotly or Vega-Lite fields)?
  - Does the chart spec's data match the rows returned by the SQL query (correct columns as axes)?
  - When a specific chart type was requested, does the spec use that type?
  - Is the prose answer free of invented data values not present in the query results?
- expect_tools: [execute_sql, generate_chart_spec, finish]
- forbid_tools: []

## Notes

- `generate_chart_spec` is an in-process tool that takes `query_results` (list of dicts from `execute_sql`), `chart_type` (bar/line/scatter/pie/histogram), `x_col`, `y_col` (or `value_col` for pie/histogram), and optional `title`. It builds the JSON dict in Python and returns it as a JSON string.
- The web UI detects the presence of a `chart_spec` key in the `finish` answer's JSON envelope and renders it with `react-plotly.js`. No external charting server is contacted.
- Vega-Lite is an alternative output format; default to Plotly for the demo gate since `react-plotly.js` is the UI dependency. Vega-Lite support can be added later.
- Statistical functions (correlation, std dev, percentiles) are computed via SQLite's built-in aggregates (AVG, SUM, COUNT, MIN, MAX, GROUP BY). More advanced statistics (Pearson r, IQR) are approximated via multiple queries or returned as descriptive prose; no Python math library is required.
- Out of scope: 3-D charts, geographic maps, animated / time-slider charts, server-side image rendering (PNG/SVG export), custom colour themes.
