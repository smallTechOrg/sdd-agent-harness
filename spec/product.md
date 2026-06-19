# Product

> Filled by the **spec-writer** from intake. Part 1 of the 4-part spec contract (see `harness/harness.md`).

## What it does

DataChat is a conversational data-analysis agent for users who need to explore datasets without writing SQL or code. Users upload one or more CSV or JSON files through a web UI; the agent ingests them into a local SQLite database and infers the schema automatically. From that point the user can ask questions in plain English — "Which products had the highest return rate last quarter?" or "Show me a breakdown of revenue by region" — and the agent translates each question into a read-only SQL query, runs it, and returns a plain-language answer plus an optional interactive chart (Plotly/Vega-Lite JSON spec). Conversation is multi-turn: follow-up questions ("Now filter for Europe only") carry forward the context of earlier turns, so users can drill down without repeating themselves. Every run is observable: tool calls, model hops, and timing are recorded as OTel spans and rendered at the built-in `/traces` endpoint.

## Success criteria (these feed the outcome eval — keep them testable)

- [ ] After a user uploads a CSV or JSON file, the agent can answer a natural-language question about that file's data within the same session, returning a factually correct answer derived from a SQL query over the uploaded rows.
- [ ] When asked a question that can be answered with a chart, the agent returns a valid Plotly/Vega-Lite JSON spec alongside the prose answer, and the chart renders correctly in the web UI without errors.
- [ ] In a multi-turn conversation, a follow-up question that references the prior turn (e.g. "now filter for Europe") produces a SQL query that correctly applies the additional constraint, demonstrating that conversation context is maintained.
- [ ] When a user asks a question the agent cannot answer from the uploaded data (e.g. asking about a column that does not exist), the agent says so clearly rather than fabricating a result.
- [ ] The `execute_sql` tool is restricted to read-only queries (SELECT only); any attempt to run a mutating query (INSERT, UPDATE, DELETE, DROP) is refused with a safe message.

## Domain instructions (the agent's system-prompt guidance for this domain)

You are DataChat, a precise and helpful data-analysis assistant. You help users understand their uploaded datasets by translating their natural-language questions into SQL queries and presenting results clearly.

Rules you must always follow:

1. Only query data that has been uploaded in this session. Never invent, assume, or hallucinate data values, column names, or table names. If you are unsure whether a column exists, call `get_dataset_schema` first.
2. Only use SELECT statements with `execute_sql`. Never generate or run INSERT, UPDATE, DELETE, DROP, CREATE, or any other mutating SQL. If asked to modify or delete data, explain that you are a read-only analysis tool.
3. Before writing a SQL query, call `list_datasets` (if you do not already know which datasets are loaded) and `get_dataset_schema` (to confirm column names and types). Never guess a column name.
4. When the user's question is naturally answered with a chart, call `generate_chart_spec` after `execute_sql` to produce a Plotly/Vega-Lite JSON spec. Include the chart spec in your final answer.
5. In multi-turn conversations, use the prior messages to understand what the user is refining or following up on. Do not ask the user to repeat context that is already in the conversation.
6. Be concise and direct. Lead with the answer, then explain the SQL or methodology only if the user asks.
7. If a question is out of scope (e.g. asks you to write code, access external URLs, or perform actions outside data analysis), decline politely and redirect to what you can do.
8. Call `finish` exactly once, after you have the complete answer (prose + optional chart spec). Do not call `finish` before you have queried the data.

## Primary journey (Web UI)

The single combined view has two panels side-by-side (or stacked on mobile):

1. **Upload panel** (left / top) — A drag-and-drop or file-picker zone that accepts `.csv` and `.json` files. The user selects one or more files and clicks "Upload". Progress is shown inline. On success, the panel lists the ingested datasets with their detected schema (column names + types + row count). The panel stays accessible so additional files can be added at any time.

2. **Chat panel** (right / bottom) — A standard chat thread that becomes active once at least one dataset is loaded. The user types a natural-language question and presses Enter or clicks Send. The question is posted to `POST /runs` (SSE stream preferred so tokens appear as they arrive). The answer renders in the chat thread as Markdown; if a chart spec is present it renders inline as an interactive Plotly chart. Each message includes a small "trace" link that deep-links to `/traces` filtered to that run_id, so the user can inspect the exact SQL and tool calls. The conversation is multi-turn: the thread accumulates messages and context is maintained via the LangGraph short-term memory checkpointer.

## Out of scope (Future Phases)

- Persistent user accounts and cross-session dataset storage (datasets exist only for the current session).
- Writing to or mutating the uploaded data (append rows, edit values, delete records).
- External data sources (databases, REST APIs, cloud storage) — local uploads only.
- Python/pandas/code-execution sandbox; all computation is SQL-based.
- Scheduled or automated queries (cron, webhooks).
- Multi-user collaboration or shared datasets.
- Export of results to file (CSV download, PDF report).
- Natural-language-to-dbt or natural-language-to-pipeline generation.
