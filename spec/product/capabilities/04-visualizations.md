# Capability: Visualizations (Charts)

## What It Does

When a question's answer is better shown as a chart (a trend, a comparison across categories, a
distribution), the agent proposes a **chart spec** describing how to plot the result table it already
computed. The backend attaches that spec to the assistant turn; the frontend renders it (Recharts)
alongside the text answer and the result table. No new data leaves the deployment — the chart is built
from the rows the `run_sql` tool already returned.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | string (NL) | user (chat turn) | yes |
| last result table | columns + rows (JSON) | the agent's last successful `run_sql` (graph state) | yes |
| chart intent | tool call args (chart_type, x, y, title) | the agent (Gemini) | yes (when a chart fits) |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| chart spec | `{ "type": "bar\|line\|pie", "title": str, "x": str, "y": str, "data": [{x, y}, …] }` | SSE `answer` event → UI; persisted on the `message` (`chart_json`) |

## How it works (within the existing ReAct loop)

The agent gains one more tool, exposed as an **MCP tool** alongside `inspect_schema` / `run_sql`:

- **`suggest_chart(chart_type: str, x_column: str, y_column: str, title: str)`** — flat string args
  (Gemini-friendly; no nested schema). The executor builds a chart spec from the **last successful
  `run_sql` result** in state, mapping `x_column`/`y_column` to that table's columns. It is a
  **read-only, pure transform** of data already retrieved — it touches no external system.

The agent typically: `inspect_schema` → `run_sql` (get the rows) → `suggest_chart` (when a chart helps)
→ `finish`. Charts are **optional**: for a single-number or non-plottable answer the agent skips
`suggest_chart` and the turn has no chart.

## Business Rules

- A chart is built **only** from a column subset of the agent's last successful `run_sql` result —
  never from new data or a separate query path. If the named columns aren't in that result, the tool
  returns an error value the loop observes and can correct from (self-correction,
  [`../../engineering/patterns/react-agent.md`](../../engineering/patterns/react-agent.md)).
- `chart_type` is constrained to `bar` | `line` | `pie`; an unknown type is rejected as an error value.
- Charts are additive: the text answer + result table remain the primary output; the chart is a view of
  the same rows. A turn without a chart is fully valid.
- The chart spec is small (the already-capped result rows) and persisted with the assistant `message`
  so reloading the conversation re-renders it.

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Google Gemini | decides whether/how to chart (`suggest_chart` tool call) | LLM down → fatal → `handle_error` (same as any plan step) |
| `suggest_chart` tool (in-process / MCP) | build a chart spec from the last result table | bad column/type → error value appended → loop retries or skips the chart |

## Success Criteria

- [ ] For "sales by region", the agent calls `suggest_chart` and the assistant turn carries a `chart`
      spec with `type` in {bar,line,pie}, a non-empty `data` array, and `x`/`y` matching result columns
      (eval/integration test, real Gemini, loose assert).
- [ ] A `suggest_chart` call naming a column not in the last result returns an error value and does not
      crash the run.
- [ ] A single-number answer (e.g. "what is the total?") completes with **no** chart and no error.
- [ ] The frontend renders the chart in the chat thread (Playwright asserts an SVG/chart node appears
      in the post-JavaScript DOM for a charted answer).
- [ ] A reloaded conversation (`GET /conversations/{id}`) re-renders persisted charts.
