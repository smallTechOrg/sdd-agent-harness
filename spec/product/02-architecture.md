# Architecture

## System Overview

DataChat is an async **FastAPI** + **SSE** service fronting a **Next.js/React/Tailwind** chat UI
([`06-ui.md`](06-ui.md), Phase 3). A user creates
a dataset and uploads CSV files; the backend parses each CSV, infers its schema, and materializes it as
a table in an in-process **DuckDB** analytical engine. The user then chats about the dataset: each
question runs a **LangGraph ReAct agent** that uses **Google Gemini** (`gemini-2.5-flash`) to inspect
the schema and generate a **read-only SQL query**, executes it via an **MCP tool** against DuckDB, and
streams back a plain-English answer plus the result table over **SSE**. App metadata (datasets, files,
conversations, messages, runs) lives in **SQLite**; the CSV-derived data lives in DuckDB. This is
the single-ReAct-loop default of the agentic stack
([`../engineering/agentic-architecture.md`](../engineering/agentic-architecture.md)) — every baseline
layer real from Phase 1.

## Agentic Stack Layers Used

| Layer | Used? | Why / notes |
|-------|-------|-------------|
| 1 Model | ✅ baseline | Google **Gemini `gemini-2.5-flash`** via `init_chat_model` (provider pinned in [`../engineering/tech-stack.md`](../engineering/tech-stack.md)); `GEMINI_API_KEY`/`GOOGLE_API_KEY` required. No model routing — one model fits the NL→SQL task. |
| 2 Context | ✅ baseline | System prompt assembles: SQL-analyst role + read-only contract + dataset **schema** + a small **row sample** + recent conversation turns + the loop's `action_history`. Built once in `context.build(...)` — [`memory-and-context.md`](../engineering/patterns/memory-and-context.md). |
| 3 Memory — working/short-term | ✅ baseline | **Working** = LangGraph `AgentState` (`action_history`, query results) per run. **Short-term** = conversation turns (`messages` table) + the session-scoped DuckDB connection keyed by dataset/conversation, enabling multi-turn follow-ups. |
| 3 Memory — long-term | ❌ no | The agent does not need to remember anything across conversations; each conversation is self-contained against one dataset. Deferred (Future Phases). |
| 4 Tools / MCP | ✅ baseline | Real **MCP tools** over the dataset's DuckDB: `inspect_schema` (list tables/columns/types + sample rows), `run_sql` (execute a **read-only** SELECT), and `suggest_chart` (build a bar/line/pie spec from the last result — Phase 3, [`capabilities/04-visualizations.md`](capabilities/04-visualizations.md)). Plus the structured `finish` tool. Local `stdio` MCP server in `mcp/servers/`. |
| 5 Retrieval / RAG | ❌ no | Answers come from running SQL over structured data, not from an unstructured knowledge corpus. No embeddings/vector store. Deferred. |
| 6 Multi-agent | ❌ no | A single ReAct loop keeps NL→SQL coherent; no sub-task decomposition needs separate agents. Default single-agent ([`react-agent.md`](../engineering/patterns/react-agent.md)). |
| 7 Guardrails — action-safety | ✅ baseline | Every model-generated SQL string is validated **read-only** (parse → reject non-SELECT / DDL / DML / multi-statement / dangerous functions) before execution. Defined in [`07-agent-graph.md`](07-agent-graph.md) § action-safety. |
| 7 Guardrails — input/output + HITL | ❌ no | Input is the user's own uploaded data (not untrusted third-party content), and read-only SELECTs are not irreversible/high-stakes — no human approval gate needed. Deferred. |
| 8 Durability / checkpointing | ❌ no | A run is a single short question→answer cycle (seconds); no long/resumable runs to survive a restart. No LangGraph checkpointer in v1. Deferred. |
| 9 Observability + evals | ✅ baseline | Structured per-`run_id` logs, token/cost on each `run`, **OTel GenAI traces**, and an eval skeleton (fixed CSV + reference-SQL question cases, ≥1 loose assertion, run in CI against real Gemini). |
| 10 Interface / serving | ✅ | Async **FastAPI** REST + **SSE** streaming (Phase 1) + a **Next.js + React + Tailwind** chat UI under `frontend/` with chart rendering (Phase 3, [`06-ui.md`](06-ui.md)). Trigger = HTTP API + UI. See [`05-api.md`](05-api.md). |

## Component Map

```
Next.js / React / Tailwind UI  (dataset picker + upload, chat, result tables, live trace)
        ↓  (HTTP + SSE)
Async FastAPI API  (ok()/api_error() envelope)
        ├─ Dataset/Upload service ──► CSV parse + schema inference ──► DuckDB (per-dataset tables)
        ├─ Conversation service ────► SQLite (datasets, files, conversations, messages, runs)
        └─ Agent runner: LangGraph ReAct StateGraph
               ├─ context assembly  ← short-term memory (messages) + schema/sample
               ├─ plan_action  ← Google Gemini (init_chat_model)
               ├─ act  ── MCP tools ──► [action-safety: read-only check] ──► DuckDB
               ├─ observe → loop  (until finish / max_iterations → force_finalize)
               └─ finalize → SSE stream answer + table + trace
        ↓
Observability: OTel GenAI traces · token/cost on run · structured run_id logs · eval skeleton
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Interface | FastAPI routes + SSE; Next.js chat UI. Renders streamed answer/table/trace. |
| Orchestration | LangGraph ReAct loop ([`07-agent-graph.md`](07-agent-graph.md)) — plan→act→observe until `finish`. |
| Tools / MCP | `inspect_schema`, `run_sql`, `finish` MCP tools; `run_sql` behind the read-only action-safety boundary. |
| Model | Gemini via `init_chat_model`; structured usage returned per call. |
| Memory/context | Working state + short-term conversation memory; context assembled once. |
| Analytical engine | DuckDB — executes read-only SQL over the dataset's CSV-derived tables. |
| Metadata storage | SQLite — datasets, files, conversations, messages, runs. |
| Observability | OTel traces, token/cost on runs, structured logs, eval skeleton. |

## Data Flow

1. **Trigger:** User uploads CSV(s) into a dataset via the UI/API, then sends a chat question.
2. **Setup (upload):** Each CSV is parsed, its schema (columns + inferred types) recorded in
   SQLite, and the rows loaded into a DuckDB table for that dataset.
3. **Question:** The API opens a `run`, assembles context (schema + sample + recent turns), and starts
   the ReAct loop.
4. **Loop:** Gemini plans an action (inspect schema or generate a read-only SQL query); the read-only
   guard validates it; the `run_sql` MCP tool executes it on DuckDB; the result is observed and looped
   back. The model calls `finish` when it has the answer.
5. **Output:** The final plain-English answer + result-table rows + the live `action_history` trace
   are streamed to the UI over SSE; the turn is persisted as `messages`, and usage is recorded on the
   `run`.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini API | LLM for the ReAct loop (NL→SQL planning + answer) | Fail loud; the run records `error`, API returns `api_error("LLM_UNAVAILABLE", …)`. |
| SQLite | App metadata (datasets, files, conversations, messages, runs) | Startup fails loud if unreachable; request returns `api_error`. |
| DuckDB (file-backed, one per dataset) | Analytical engine executing read-only SQL over dataset data; persists across restarts | If the dataset's DuckDB file is missing (e.g. deleted), API returns a clear "dataset not loaded — please re-upload" error, not a 500. |

## Deployment Model

A long-running async FastAPI service (uvicorn) plus the Next.js frontend. DuckDB runs **in-process**
inside the API service; SQLite is an external service. Single-node, single-deployment for the first
release (no horizontal scale-out of the in-process DuckDB engine).
