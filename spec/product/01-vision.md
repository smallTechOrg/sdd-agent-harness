# Vision

## What This Agent Does

**DataChat** is a data-analysis agent. A user creates a named **dataset**, uploads one or more CSV
files into it, and then asks **natural-language questions** about that data in a **multi-turn chat
conversation**. The agent inspects the dataset's inferred schema, translates each question into a
**read-only SQL query**, runs it against an analytical engine (DuckDB) over the uploaded data, and
answers with a plain-English explanation plus the **result rows as a table**. Follow-up questions
("now filter that to 2024", "what about by region?") build on prior turns in the same conversation.

## Who Uses It

Data analysts and non-technical "data-literate" users — people who have CSV exports (sales,
operations, survey results) and need answers from them, but who do not want to hand-write SQL or build
pivot tables. They think in questions ("which region grew fastest last quarter?"), not in `GROUP BY`
clauses.

## Core Problem Being Solved

Today, getting an answer from a CSV means opening a spreadsheet and building pivot tables by hand, or
writing SQL/pandas — slow, error-prone, and out of reach for non-technical users. Each new question
means new manual work, and follow-up questions restart the cycle. DataChat replaces that manual
query-writing loop with a conversation: ask in English, get an explained answer and a result table,
then refine by asking again.

## Success Criteria

- [ ] A user can create a dataset, upload ≥1 CSV, and the system infers and reports each column's name
      and type without manual schema entry.
- [ ] For a known dataset, a single NL question (e.g. "total sales by region") returns a correct
      answer whose result table matches a hand-written reference SQL query (verified by an eval case).
- [ ] A multi-turn follow-up ("now just 2024") produces a result that correctly narrows the previous
      turn's answer — i.e. prior conversation turns measurably change the generated query.
- [ ] Every answer includes a plain-English `description` of what the agent did for each step (the
      live trace), never only raw SQL.
- [ ] No question can mutate or read outside the dataset: every generated query is verified read-only,
      and only the dataset **schema + a small sample of rows** (never the full data) is sent to the LLM.

## What This Agent Does NOT Do (Out of Scope)

- **No file formats other than CSV** in the first release (no JSON, Excel, Parquet, database
  connectors).
- **No auto-generated narrative "insights"** — it answers the question asked; it does not volunteer
  trends or recommendations.
- **No cross-dataset joins** — a conversation queries exactly one dataset.
- **No data larger than memory** — datasets are assumed to fit comfortably in DuckDB's in-process
  engine on one machine.
- **No write/DDL/DML against the data** — queries are strictly read-only `SELECT`.
- **No long-term memory or retrieval/RAG** — the agent remembers within a conversation only, and uses
  no external knowledge corpus.
- **No multi-tenant auth/roles beyond a basic single-deployment model.**

## Key Constraints

- **Read-only queries only.** Every model-generated query passes a read-only safety check before it
  runs (see [`07-agent-graph.md`](07-agent-graph.md) § action-safety boundary). No `INSERT`,
  `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ATTACH`, `COPY`, `PRAGMA`, or multi-statement input.
- **Schema + sample only to the LLM.** The LLM sees the dataset's inferred schema (column names +
  types) and a small sample of rows (e.g. ≤20) for grounding — **never the full dataset**. Answers
  come from running SQL on the full data locally, not from the LLM "reading" the data.
- **`GEMINI_API_KEY` (alias `GOOGLE_API_KEY`) is required.** There is no offline/stub mode; the agent
  fails loud at startup if the key is missing (the model layer is real from Phase 1 —
  [`../engineering/agentic-architecture.md`](../engineering/agentic-architecture.md)).
- **File-backed analytical engine.** DuckDB holds the per-dataset tables in a file per dataset; data
  survives a process restart, and a missing file is reported as "dataset not loaded — please re-upload"
  (see [`04-data-model.md`](04-data-model.md) § Data Lifecycle).
- **Bounded agent loop.** The ReAct loop is capped by `max_agent_iterations` and force-finalizes
  rather than looping forever ([`07-agent-graph.md`](07-agent-graph.md)).

## Phases of Development

| Phase | Description | Success Gate |
|-------|-------------|--------------|
| 1 | **Core loop, real end-to-end.** Create dataset + upload CSV(s) → schema inferred + loaded into DuckDB; multi-turn NL→SQL ReAct agent (Gemini) answers questions via a read-only SQL MCP tool + a schema-inspection tool; conversation history persists; SSE-streamed answer + result table + live trace; baseline memory (working + short-term), action-safety guardrail, OTel traces + token/cost on the run, and an eval skeleton — **all real.** | Upload a known CSV, ask a question whose result table matches a reference SQL query; ask a follow-up that narrows it correctly; the loop runs ≥2 iterations (an action, then `finish`) and force-finalizes when driven past `max_agent_iterations`; an illegal (non-read-only) query is rejected by the safety check. |
| 2 | **Hardening & usability** (earns its place after Phase 1 ships): richer error surfacing for ambiguous questions, larger-CSV handling, query-history view, and an expanded eval suite. | Eval suite passes on a held-out question set; ambiguous questions get a clarifying response, not a wrong table. |
| 3 | **Chat UI + visualizations.** Next.js + React + Tailwind chat UI ([`06-ui.md`](06-ui.md)) over the existing HTTP/SSE API: dataset picker + CSV upload, multi-turn chat with live agent trace, rendered result tables, and **charts** ([`capabilities/04-visualizations.md`](capabilities/04-visualizations.md)) — the agent proposes a bar/line/pie chart for a result via a `suggest_chart` tool; the UI renders it. | A Playwright browser test drives the real stack: create a dataset, upload a CSV, ask a question, and assert the answer text + result table + a chart node appear in the post-JavaScript DOM. |

## Future Phases

Deferred beyond the first release — each is one line here, not a capability:

- **Other file formats** — JSON, Excel, Parquet, direct database connectors (CSV only in MVP).
- **Auto-generated narrative insights / summaries** of a dataset.
- **Cross-dataset joins** and querying multiple datasets in one conversation.
- **Large-scale data** that exceeds memory (out-of-core / external storage).
- **Long-term memory across conversations** (remembering a user's prior findings or preferences).
- **Retrieval / RAG** over a documentation or knowledge corpus.
- **Full multi-tenant auth, roles, and quotas** beyond a basic single-deployment model.
