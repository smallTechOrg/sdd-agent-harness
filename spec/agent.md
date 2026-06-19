# Agent layers

> ON = generated in this phase. Default baseline is ON and real. Turn an optional layer ON only when a
> capability needs it; name that capability in Why. Each layer maps to one recipe in harness/patterns/.

| Layer | Recipe | Default | This build | Why (capability) |
|-------|--------|---------|-----------|------------------|
| 1 · Model & providers | model-and-providers.md | ON | ON | google_genai / gemini-2.5-flash (cheap tier); JSON-mode structured output used by generate_chart_spec to return a typed Plotly/Vega-Lite spec |
| 2 · Context engineering | context-engineering.md | ON | ON | dataset schema summaries (column names, types, row counts) injected into context each turn so the model never guesses column names; long tool-result messages trimmed to stay within token budget |
| 3 · Memory (short-term) | memory.md | ON | ON | LangGraph AsyncSqliteSaver checkpointer keyed to thread_id — required by multi-turn-conversation capability |
| 3 · Memory (long-term, cross-run) | memory.md | OFF | OFF | datasets exist only within the current session; no cross-run recall needed |
| 4 · Tools (in-process) | tools-and-mcp.md | ON | ON | list_datasets, get_dataset_schema, execute_sql, generate_chart_spec, finish — all local, no external process |
| 4 · Tools (MCP, external) | tools-and-mcp.md | OFF | OFF | no external integrations; all data is local |
| 5 · Retrieval / RAG | retrieval.md | OFF | OFF | no corpus to embed; data is in SQLite tables queried directly via execute_sql |
| 6 · Multi-agent | multi-agent.md | OFF | OFF | a single ReAct loop handles all four capabilities; no distinct sub-task requiring isolation |
| 7 · Guardrails & HITL | guardrails-and-hitl.md | OFF | ON | on_tool_call hook validates execute_sql argument is a SELECT-only statement before it runs; on_input scans for PII in uploaded data names (nl-query capability, action-safety boundary) |
| 8 · Durability (checkpointer) | durability.md | OFF | OFF | runs are short (single question → answer); crash recovery not needed; short-term memory checkpointer is the AsyncSqliteSaver used for multi-turn, not a durability checkpoint |
| 9 · Observability & Evals | observability-and-evals.md | ON | ON | OTel spans for every execute_sql, generate_chart_spec, and LLM call; outcome eval grades the final answer against EARS criteria; trajectory eval confirms execute_sql fired and no mutating tool ran |
| 10 · Interface / serving | interface.md | ON | ON | FastAPI: GET /health, POST /runs (accepts optional thread_id), POST /upload (multipart CSV/JSON ingest), GET /traces; SSE streaming on POST /runs/stream for token-by-token answer in chat panel; Next.js + React + Tailwind web UI |
| — · Persistence (data spine) | persistence.md | ON | ON | runs, messages, spans (core) + datasets, uploaded_files (domain tables); uploaded CSV/JSON rows stored in dynamically created SQLite tables |
| 11 · Deploy & Operate | deploy.md | later | later | langgraph.json + Dockerfile ship with the build; host TBD (Railway recommended) at /deploy |

## Guardrails trigger set (Layer 7 — action-safety baseline, HITL OFF)

The following actions are validated by the `on_tool_call` guardrail before execution. HITL pause is NOT activated (no money, no prod-data deletes, no external comms in scope):

- `execute_sql` — the SQL argument must begin with SELECT (case-insensitive, after stripping whitespace and SQL comments). Any other statement is blocked and returns a safe refusal message. This is enforced both in the guardrail hook and as an application-level check inside the tool itself (defence in depth).

## Domain tables (beyond runs/messages/spans)

- `datasets` — id (str PK), name (str, unique within session), created_at (datetime), row_count (int), column_info (JSON — list of {name, type, sample_values})
- `uploaded_files` — id (str PK), dataset_id (str FK → datasets.id), original_filename (str), stored_path (str), created_at (datetime)
- Dynamic data tables — one SQLite table per uploaded file, named from the sanitised filename (e.g. `sales_q4_csv`), containing the actual data rows. These are created at upload time and dropped/replaced on re-upload of the same name.

## Notes

- Short-term memory (AsyncSqliteSaver) is ON for multi-turn-conversation; this is distinct from Layer 8 Durability. The checkpointer stores conversation state per thread_id; runs are still short enough that crash recovery (durability proper) is not warranted.
- The `generate_chart_spec` tool returns a JSON string. The `finish` tool embeds it under a `chart_spec` key in its answer payload. The web UI detects this key and renders the chart with react-plotly.js.
- `execute_sql` result truncation to 50 rows is enforced in the tool, not by the guardrail. The guardrail's job is statement-type validation only.
- Multi-turn context window: the context engineering layer trims tool-result messages (especially long SQL result sets) from older turns while keeping all human/assistant messages, to stay within gemini-2.5-flash's context window without losing conversation intent.
