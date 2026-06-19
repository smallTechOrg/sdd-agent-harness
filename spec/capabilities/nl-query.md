# Capability: Natural-Language Query

## What & why

The user types a question in plain English — "What were the top 5 products by revenue?" — and the agent translates it into a read-only SQL query, executes it against the uploaded SQLite tables, and returns a clear prose answer derived from the actual query results. This is the core value of DataChat: removing the SQL barrier between a user and their data. It serves the first and fourth success criteria in `spec/product.md` (correct answers from uploaded data; honest "I don't know" when the data cannot answer).

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user asks a natural-language question about an uploaded dataset the system SHALL call `get_dataset_schema` to confirm column names, then call `execute_sql` with a valid SELECT query, and return an answer derived solely from the query results.
- WHEN the SQL query returns zero rows the system SHALL report that no records matched the question's conditions rather than fabricating data.
- IF the user's question references a column that does not exist in any loaded dataset THEN the system SHALL call `get_dataset_schema`, discover the mismatch, and respond with a message naming the available columns rather than guessing.
- IF the agent attempts to run a mutating SQL statement (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE) THEN the system SHALL refuse to execute it and return a safe message stating that only read-only queries are permitted.
- WHEN no dataset has been uploaded yet and the user asks a data question the system SHALL call `list_datasets`, find it empty, and instruct the user to upload a file before querying.
- WHEN the query result set has more than 50 rows the system SHALL summarise the results (e.g. "showing the first 50 of 312 rows") rather than dumping all rows into the answer.

## Tools & layers touched

- tool: `list_datasets` (in-process @tool — discover which tables are available)
- tool: `get_dataset_schema` (in-process @tool — confirm column names, types, sample rows before writing SQL)
- tool: `execute_sql` (in-process @tool — run a read-only SELECT; enforces a SELECT-only allowlist guard)
- tool: `finish` (in-process @tool — emit the final prose answer)
- Guardrails: `on_tool_call` hook validates the SQL argument of `execute_sql` is a SELECT statement before it runs — `harness/patterns/guardrails-and-hitl.md`

## Evaluation

- outcome evaluation_steps:
  - Does the answer directly address the user's question using data from the uploaded dataset?
  - Is the answer free of invented column names, table names, or data values not present in the query results?
  - When the data cannot answer the question, does the response say so clearly rather than guessing?
  - Is a SQL SELECT query visible in the run's trajectory (via execute_sql span)?
- expect_tools: [get_dataset_schema, execute_sql, finish]
- forbid_tools: []

## Notes

- The `execute_sql` tool must enforce SELECT-only at the implementation level (parse the first non-whitespace keyword; reject if not SELECT). The guardrail `on_tool_call` hook adds a second layer of enforcement so even a prompt-injection that tricks the model cannot trigger a write.
- Result truncation: the tool caps result rows at 50 in the returned string; the full count is returned alongside so the agent can report "N total rows".
- Aggregation answers (SUM, AVG, COUNT) should present the computed scalar clearly in prose, not just repeat the SQL.
- Out of scope: cross-dataset JOINs in a first pass (the model may attempt them but no special tooling supports them); query optimisation or index advice; running arbitrary Python against the data.
