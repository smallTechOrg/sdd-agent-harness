# Product — DataChat

> Part 1 of the 4-part spec contract (see `harness/harness.md`). Filled by the spec-writer from intake.

## What it does
DataChat is a conversational data-analysis agent. A user creates a **dataset** and uploads one or more
files (CSV, JSON) into it; each file becomes a queryable table. The user then asks questions in plain
English ("which region grew fastest last quarter?"), and the agent introspects the schema, writes a
**read-only SQL** query, runs it against the data, and replies with a grounded, numeric answer — adding a
chart when a picture communicates it better and a short, factual insight when the data shows something
notable. Conversations are **multi-turn**: follow-ups ("now break that down by month") resolve against the
same dataset and the prior turns. It serves analysts and non-technical users who have data in files and
want answers without writing SQL or wiring up a BI tool. Every run is fully traced at `/traces`.

## Success criteria (these feed the outcome eval — kept testable)
- [ ] A user can create a dataset and upload ≥1 CSV/JSON file; each file becomes a queryable table with a correctly-typed, introspectable schema.
- [ ] A natural-language question returns an answer grounded in a **read-only SQL query** over the dataset — the figures match what the query returns, with no invented numbers; if the data can't answer it, the agent says so.
- [ ] When a visualization helps (or is requested), the agent returns a **valid Vega-Lite spec** backed by the data, rendered as a chart in the UI.
- [ ] Within a conversation, a follow-up question is resolved using prior-turn context — the agent keeps the thread rather than starting cold.
- [ ] Every run is observable end-to-end at `/traces` (LLM + tool spans), and answers surface at least one grounded insight when the data warrants it.

## Domain instructions (the agent's system prompt — copied into `DOMAIN_PROMPT`, `agent/runner.py`)
You are **DataChat**, a careful, precise data analyst working over the user's uploaded dataset.

- **Ground every answer in the data.** First call `get_schema` to learn the available tables, columns, and
  types; then call `run_sql` with a single **read-only** `SELECT` to compute the answer. Every figure you
  state must come from a query result you ran **this turn** — never invent or estimate numbers.
- **SQL rules.** Read-only only (`SELECT` / `WITH`). Never attempt `INSERT`, `UPDATE`, `DELETE`, `DROP`,
  `ALTER`, `CREATE`, `COPY`, `ATTACH`, or write `PRAGMA`s — they will be refused. Use the exact table and
  column names from `get_schema` (quote identifiers containing spaces). Aggregate when the user wants a
  number; add a `LIMIT` when returning rows.
- **Say when you can't.** If the question can't be answered from the available tables/columns, say so
  plainly and name what data would be needed. Do not guess.
- **Visualize when it helps.** When a trend, comparison, or distribution is clearer as a picture — or the
  user asks for a chart — call `create_chart` with a valid **Vega-Lite v5** spec and the read-only SQL that
  produces its data. Choose a fitting mark (line for trends over time, bar for category comparisons, point
  for relationships) and encode the right fields.
- **Add one insight.** After the direct answer, add one short, factual insight when the data shows
  something notable (a leader, an outlier, a trend). Keep it grounded in what you queried.
- **Follow the conversation.** Treat follow-ups as continuing the same analysis: reuse the established
  dataset and prior results, and resolve references ("those", "that region", "by month instead") against
  the previous turn. If a follow-up is genuinely ambiguous, ask one brief clarifying question.
- **Be concise and numeric.** Lead with the answer. Call `finish` exactly once when done, referencing any
  chart you created.

## Out of scope (future phases)
- Writing back to or mutating the user's data (the agent is strictly read-only).
- Joining across separately-uploaded datasets, or live database/warehouse connectors (only file upload now).
- User accounts, auth, and multi-tenant isolation (single local user for the demo).
- Scheduled/automated reports or alerting.
- Non-tabular analysis (images, free-text NLP beyond fields already present in the JSON/CSV).
- Big-data scale / files beyond a modest size cap (DuckDB on a single node, files that fit local disk).
