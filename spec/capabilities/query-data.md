# Capability: Query the dataset in natural language

## What & why
The user asks a question in plain English; the agent introspects the dataset schema and runs a **read-only
SQL** query to compute a grounded, numeric answer. This is the product's core behaviour and the **demo-gate
capability** — the run whose answer the outcome eval grades. It realizes the "query your dataset in natural
language" success criterion in `spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN the user asks a question answerable from the dataset the system SHALL ground its answer in the result of a read-only SQL query it executed over the dataset's tables (a brief grounded insight alongside the figure is expected, not a violation).
- WHEN the answer states a figure the system SHALL ground that figure in a query result and not invent numbers.
- IF the question cannot be answered from the available tables/columns THEN the system SHALL say it cannot and name the missing data rather than guess.
- IF a generated SQL statement is not read-only (any write/DDL) THEN the system SHALL refuse to execute it and SHALL NOT mutate the data.

## Tools & layers touched
- tool: `get_schema`  (in-process @tool — returns tables, columns, types, sample rows; `harness/patterns/tools-and-mcp.md`)
- tool: `run_sql`     (in-process @tool — executes one read-only SELECT on the dataset's DuckDB, capped rows/time; `harness/patterns/tools-and-mcp.md`)
- layers: guardrails (action-safety) ON — read-only SQL enforcement, refusing any write/DDL — `harness/patterns/guardrails-and-hitl.md`

## Evaluation
- outcome evaluation_steps:  # LLM-judge scores the final answer 0–5 against the EARS criterion
  - Does the answer directly address the question asked (correct value)?
  - Is the key figure grounded in a read-only SQL query over the dataset (not invented)?
  - A brief grounded insight alongside the figure is acceptable/expected and must NOT lower the score.
- expect_tools: [run_sql]          # the run MUST execute a query to ground the answer
- forbid_tools: []                 # no mutating tool exists; `run_sql` is read-only by construction

## Notes
- Read-only is enforced structurally (DuckDB connection opened `read_only=True`) **and** by a statement
  allowlist (`SELECT`/`WITH`/`EXPLAIN`/`DESCRIBE` only) before execution; the refusal-of-writes EARS line is
  covered by a deterministic unit test (a write statement is rejected, no rows mutated), independent of the
  live model's wording. This EARS line is **intentionally** graded by that unit test rather than the
  outcome/trajectory pair: no mutating tool exists for the trajectory check to forbid (`forbid_tools: []` is
  correct by construction), so the "one EARS ⇒ one outcome + one trajectory" rule is satisfied here by a
  deterministic assertion instead.
- `get_schema` is expected first per the domain prompt but is **not** hard-required by the trajectory check
  (the gate stays robust to path variance — `harness/workflows/gates.md`); `run_sql` is the load-bearing
  grounding action and is required.
- Demo-gate goal (a real success-criterion task over the seeded demo dataset) is fixed at build time, e.g.
  "Which category has the highest total sales?" — the answer must match the query result.
