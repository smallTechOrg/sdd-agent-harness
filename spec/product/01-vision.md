# Vision

## What This Agent Does

A web-based data analysis agent that lets users connect **datasets**, then ask natural language questions about them in persistent sessions. Under the hood, the agent speaks the **Model Context Protocol (MCP)**: each dataset is wrapped by an in-process MCP **server**, and the LangGraph ReAct loop acts as an MCP **client**, discovering and invoking that server's capabilities iteratively to answer the user's question from the full data.

A **tool is a named dataset** addressed by a URI. A dataset is either an **internal directory of related Parquet files** (`parquet:///{name}`, one uploaded CSV → one Parquet → one table) or an **external database** (`postgresql://…`, BETA — see below). The dataset's MCP server exposes **one capability per table** (each backed by a read-only SQL query over DuckDB), so the LLM addresses data with a two-level call: `{"tool": "<dataset>", "capability": "<table>", "arguments": {"query": "SELECT …"}}`. The **tool's canonical name is the dataset name**. Because all of a dataset's tables are views in one DuckDB connection, a capability may JOIN that dataset's other tables; joining across separate datasets happens across ReAct iterations.

For v0.1 a dataset is created by uploading a CSV and giving it a name; existing datasets accept more CSVs (each new CSV adds a table). External **PostgreSQL** is **BETA**, gated behind the `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` flag (default off). Other external types (MySQL, document stores such as MongoDB) are deferred — document stores are non-SQL and do not fit the table/SELECT model. Future dataset types slot in by adding new connectors and MCP servers — no changes to the agent loop or UI shell.

## Who Uses It

Data analysts, business users, and developers who have tabular data and want to ask plain-English questions without writing SQL or Python. They connect a dataset once, then open sessions to interrogate it repeatedly.

## Core Problem Being Solved

Querying and exploring data typically requires coding skills (pandas, SQL, REST clients) or expensive BI tools. This agent removes that barrier: a user connects a dataset once, then asks questions in plain English across as many sessions as they like. The modular connector design means the same pattern extends to external databases (PostgreSQL today, BETA) and other sources without rebuilding the agent.

## Success Criteria

- [x] User can upload a CSV file as a named dataset and see it listed on the home page
- [ ] User can add more CSVs to an existing dataset, each becoming a new table (capability)
- [ ] User can connect an external PostgreSQL dataset by URI when external datasets are enabled (BETA)
- [x] User can start a new session on a dataset and ask natural language questions
- [x] User can return to any previous session and continue asking questions
- [x] The agent uses a ReAct loop to run SQL queries iteratively against the full dataset and self-corrects on SQL errors
- [ ] The agent addresses data with a two-level call (`tool` = dataset, `capability` = table) and may JOIN tables within the same dataset
- [x] Each query is stored in SQLite with the question, answer, SQL trace, token usage, and cost estimate
- [x] The app runs fully in stub mode without an API key
- [x] Tools are exposed by a per-dataset MCP server (one capability per table) and discovered by the agent at runtime via the MCP client — not hardcoded
- [ ] Creating a dataset connection-checks the URI and fails loudly — a broken dataset is never persisted
- [x] Home page lists all datasets; each dataset shows its tables and its sessions

## What This Agent Does NOT Do (Out of Scope for v0.1)

- External dataset types beyond PostgreSQL — MySQL and document stores (e.g., MongoDB) are deferred; document stores are non-SQL and do not fit the table/SELECT model
- Non-database dataset types (REST API, GraphQL, shell) — the connector seam supports adding them; not wired up yet
- Charts, visualizations, or dashboards (deferred to Phase 4)
- AI-written insight summaries (deferred to Phase 5)
- React/Vite frontend — v0.1 uses Jinja2 templates
- User authentication or multi-user support
- Cross-dataset joins in a single capability — the agent composes those across ReAct iterations

## Key Constraints

- OpenRouter API key is optional — app runs in stub mode without it
- SQLite only for app state — no PostgreSQL required to run (external PostgreSQL datasets are a separate, optional, flag-gated BETA feature)
- A tool is a named dataset addressed by a URI; the tool's canonical name equals the dataset name; the MCP server exposes one capability per table
- Internal Parquet datasets store physical files keyed by dataset id (`{datasets_dir}/{dataset_id}/{table}.parquet`); the URI carries no filesystem path
- External datasets are off by default (`DATAANALYSIS_ENABLE_EXTERNAL_DATASETS`); when off the external create path is rejected (501) and the UI hides the option
- Creating, adding a CSV, or syncing a dataset runs a connection check and fails before commit; a broken dataset is never persisted
- Dataset credentials (e.g., PostgreSQL URIs) are never logged or displayed — every rendering strips credentials
- All commands run from the repo root with `uv run` prefix
- SQL execution is read-only (`SELECT` only); non-SELECT SQL is rejected
- Tool/capability input schemas are auto-generated by the MCP server (FastMCP) from the tool signature — not hand-written or stored

## Phases of Development

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Domain models + SQLite schema | ✅ Done (being refactored) |
| 2 | Stubbed LangGraph pipeline + FastAPI UI end-to-end | ✅ Done (being refactored) |
| 3 | MCP tool layer: per-dataset MCP servers over DuckDB (one capability per table), URI-addressed datasets, connector seam, external PostgreSQL (BETA) | 🔄 In Progress |
| 4 | Charts and visualizations | Deferred |
| 5 | AI-written insights | Deferred |
