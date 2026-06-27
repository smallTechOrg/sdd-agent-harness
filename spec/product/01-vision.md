# Vision

## What This Agent Does

A web-based data analysis agent. Users connect a **dataset** — a named directory of Parquet files built
from uploaded CSVs, or (BETA) an external PostgreSQL database — and each dataset is wrapped **1:1** by an
in-process **MCP server**. The LangGraph ReAct loop acts as an MCP **client**, running read-only SQL over
the full data to answer natural-language questions in persistent sessions.

The **primary entity is the MCP server.** Per the Model Context Protocol (2025-06-18), a server has three
kinds of children: **tools**, **resources**, and **prompts**. These are **LLM-generated** by a **sync
pipeline** that inspects the dataset and produces, in order:

1. a server **title + description**,
2. a dataset **JSONSchema** (table schemas + entity relationships),
3. **resources** — the schema itself plus the primary/secondary **entities** derived from it,
4. **tools** — "GET-API" canned **SELECT** queries over those entities,
5. **prompt templates** over those tools.

Sync is **incremental** (the LLM is shown the existing capabilities and suggests changes), **versioned**
(each sync bumps the server version), and **soft-delete-only** — a generated suggestion can never
irreversibly delete a capability.

A **dataset is not a separate entity**: its URI, type, physical-table catalog, and generated JSONSchema
all live in the MCP server's metadata. The server is bound 1:1 to a dataset URI (`parquet:///{name}` or
`postgresql://…`), enforced unique on create.

The agent answers a question with a **single-level** call `{"tool":"<server>","arguments":{"query":"SELECT
…"}}` against a generic read-only-SQL tool (Phase A). The generated GET-API tools, resources, and prompts
are exposed over an **MCP JSON-RPC endpoint** (`POST /database/{id}`) for the UI and external MCP
clients. Wiring the generated tools into the agent itself (**hybrid**: prefer a matching generated tool,
fall back to arbitrary SQL) is the near-term follow-up (Phase B).

## Who Uses It

Data analysts, business users, and developers who have tabular data and want to ask plain-English
questions without writing SQL or Python. They connect a dataset once, then open sessions to interrogate
it repeatedly — and can also consume the generated MCP server from any MCP-compatible client.

## Core Problem Being Solved

Querying data usually requires coding (pandas, SQL, REST) or expensive BI tools. This agent removes that
barrier: connect a dataset once, then ask questions in plain English across as many sessions as you like.
Modelling each dataset as a standards-compliant MCP server (with auto-generated tools/resources/prompts)
also makes the dataset reusable by the wider MCP ecosystem, and extends to external databases without
rebuilding the agent.

## The Three Primary Entities

| Entity | What it is | API module |
|--------|------------|------------|
| **MCP server** | A dataset wrapped 1:1, with LLM-generated tools/resources/prompts | `api/database.py` |
| **Session** | A long-lived conversation over one or more MCP servers (pool + memory) | `api/sessions.py` |
| **Query** | One NL question answered by a ReAct run within a session | `api/queries.py` |

## Success Criteria

- [ ] User uploads a CSV under a named dataset and an MCP server is created for it
- [ ] On create, the sync pipeline generates the server's tools, resources, and prompts (LLM, with deterministic stub offline)
- [ ] Re-syncing a server regenerates capabilities **incrementally**, bumps the version, and only **soft-deletes**
- [ ] `POST /database/{id}` answers MCP JSON-RPC `tools/list` · `tools/call` · `resources/list` · `resources/read` · `prompts/list` · `prompts/get` (with cursor pagination)
- [ ] Creating a server connection-checks the URI and fails loudly — a broken server is never persisted; the dataset↔server URI is unique (1:1)
- [ ] User starts a session over one or more servers and asks questions; the agent runs read-only SQL in a ReAct loop and self-corrects on SQL errors
- [ ] Each query is stored with question, answer, SQL trace, token usage, and cost
- [ ] The app runs fully in **stub mode** without an API key (all 5 sync stages have deterministic stubs)
- [ ] External PostgreSQL is supported (BETA) behind `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` (default off → 501)

## What This Agent Does NOT Do (Out of Scope for v0.1 / Phase A)

- The granular MCP mutation methods (`tools/add|update`, `resources/add|update`, `prompts/add|update`) with cascading partial-syncs — **specced** (capability 4 / Phase B), not implemented yet
- Wiring the generated GET-API tools into the agent loop (hybrid consumption) — Phase B
- External dataset types beyond PostgreSQL — MySQL and document stores (e.g. MongoDB) deferred; document stores are non-SQL and do not fit the table/SELECT model
- Charts/visualizations, AI-written insight summaries, a React/Vite frontend, multi-user/auth
- Cross-server SQL joins in a single call — the agent composes those across ReAct iterations

## Key Constraints

- The **MCP server is the entity**; a dataset is its metadata (URI, type, physical tables, JSONSchema). 1:1 by URI.
- Children = **tools/resources/prompts** (MCP spec). They are typed DB rows, individually addressable, versioned, soft-deletable, cursor-paginated.
- Sync is **soft-delete-only** — never hard-delete a capability; each sync bumps `version`.
- OpenRouter API key is optional — the app (and all 5 sync stages) runs in stub mode without it.
- SQLite only for app state; external PostgreSQL datasets are an optional, flag-gated BETA.
- Physical Parquet files live under `{datasets_dir}/{slug(name)}/{table}.parquet`; the URI carries no filesystem path.
- Dataset credentials (PostgreSQL URIs) are never logged or displayed — every rendering strips credentials.
- SQL execution is read-only (`SELECT`/`WITH` only); generated tool parameters bind via DuckDB parameter binding, never string interpolation.
- All commands run from the repo root with the `uv run` prefix.

## Phases of Development

| Phase | Description | Status |
|-------|-------------|--------|
| A | MCP-server entity + sync pipeline + MCP read surface + agent over generic SQL + UI | 🔄 In Progress |
| B | Granular add/update methods (cascading partial-syncs) + hybrid agent wiring | Specced (deferred) |
| — | Charts, AI insights, React frontend, auth | Deferred |
