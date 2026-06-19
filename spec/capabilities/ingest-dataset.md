# Capability: Ingest a dataset

## What & why
A user creates a named dataset and uploads one or more CSV/JSON files into it; each file is registered as a
queryable table with an introspected, correctly-typed schema. This is the entry point of the product — it
realizes the "upload your data into a dataset" success criterion in `spec/product.md`. Ingestion is an
interface + persistence behaviour (HTTP upload endpoints + DuckDB load), not an agent run, so it is graded
by a deterministic integration test rather than the LLM-judge outcome eval.

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN a user creates a dataset and uploads a CSV or JSON file the system SHALL register the file as a table and return its table name, row count, and column schema (name + type).
- WHEN multiple files are uploaded to one dataset the system SHALL register each as a separately-queryable table within that dataset.
- IF an uploaded file is unsupported or malformed THEN the system SHALL reject it with a clear error and leave the dataset's existing tables intact.

## Tools & layers touched
- endpoint: `POST /datasets`, `POST /datasets/{id}/files` (interface — `harness/patterns/interface.md`)
- store: DuckDB write-connection on the server (per-dataset analytical store); metadata in SQLite (`datasets`, `data_tables`) — `harness/patterns/persistence.md`
- layers: none beyond the base interface + persistence spine (the agent does not run during ingest)

## Evaluation
Verified by a deterministic integration test (not the LLM-judge outcome eval — there is no agent run here):
- outcome evaluation_steps (asserted in pytest, not by a judge):
  - After uploading a known CSV, the dataset reports a table whose row count and column names/types match the file.
  - Uploading a second file to the same dataset yields a second queryable table without dropping the first.
  - A malformed/unsupported file returns a clear error AND the dataset's prior tables remain queryable afterwards (assert both).
- expect_tools: []      # ingestion is an endpoint, not an agent tool call
- forbid_tools: []      # no agent run; the agent's read-only path never touches the write-connection
- **This integration test runs inside the demo-gate sequence** (alongside `/health` + the `query-data`
  outcome eval), so "demo green" proves real upload→table-registration works — not just query over a
  pre-seeded fixture.

## Notes
- The DuckDB **write** connection used to load files is server-side only and is never exposed to the agent;
  the agent gets a separate **read-only** connection (`run_sql`, see `query-data`). This is the action-safety
  boundary in `harness/patterns/guardrails-and-hitl.md`.
- Nested JSON is flattened to columns on ingest (top-level keys → columns; deeper nesting → JSON-typed
  columns the agent can query with DuckDB JSON functions). Out of scope: arbitrarily deep/ragged schemas.
- A modest per-file size cap applies (single-node DuckDB); larger-than-disk files are out of scope (`product.md`).
