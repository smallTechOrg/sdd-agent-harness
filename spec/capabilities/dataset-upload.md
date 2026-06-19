# Capability: Dataset Upload

## What & why

Users upload one or more CSV or JSON files through the web UI. The agent parses each file, infers column names and types, stores the rows in a SQLite table named after the file (sanitised), and records the dataset metadata (name, schema, row count) in the `datasets` domain table. A corresponding `uploaded_files` row tracks the original filename and stored path. Once ingested, the dataset is immediately queryable by the NL-query capability. This capability serves the first success criterion in `spec/product.md`: that an uploaded file is answerable within the same session.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN a user uploads a valid CSV file the system SHALL parse it, infer column names and types, load all rows into a new SQLite table, and record a `datasets` row with the detected column_info and row_count.
- WHEN a user uploads a valid JSON file (array of objects) the system SHALL parse it, infer schema from the keys and value types of the first non-null row, and load all records into a new SQLite table.
- WHEN a user uploads multiple files in one request the system SHALL ingest each file independently and create a separate dataset entry for each.
- IF a file is neither a valid CSV nor a valid JSON array-of-objects THEN the system SHALL return a clear error message naming the file and the rejection reason, and SHALL NOT create a partial dataset entry.
- IF an uploaded file shares a name with an existing dataset in the current session THEN the system SHALL replace the existing dataset (overwrite its rows and update the `datasets` row) and report how many rows were loaded.
- WHEN a file is successfully ingested the system SHALL respond with the dataset name, detected column names and types, and total row count.

## Tools & layers touched

- tool: `list_datasets` (in-process @tool — reads the `datasets` table, confirms the new entry is present)
- tool: `get_dataset_schema` (in-process @tool — reads column_info from the `datasets` table)
- Persistence: `datasets` and `uploaded_files` domain tables (SQLite local-first, same Base — `harness/patterns/persistence.md`)
- Interface: `POST /upload` endpoint (multipart/form-data) added alongside the standard routes — `harness/patterns/interface.md`

## Evaluation

- outcome evaluation_steps:
  - Does the response confirm the dataset was ingested and name the file?
  - Does the response include the detected column names (or a schema summary)?
  - Does the response include the row count loaded?
  - For an invalid file, does the response contain a clear rejection reason without creating a dataset?
- expect_tools: [list_datasets]
- forbid_tools: [execute_sql]

## Notes

- Column name sanitisation: strip leading/trailing whitespace, replace spaces and special characters with underscores, lowercase. Collisions get a numeric suffix (_2, _3, …).
- Table names derived from filenames: same sanitisation rules. Reserved SQLite keywords are prefixed with `t_`.
- JSON files must be a top-level array of objects. A top-level object, a scalar, or an array of scalars is rejected.
- Row count in `datasets.row_count` is the count after ingest (SELECT COUNT(*) immediately after COPY).
- Out of scope for this capability: schema evolution (adding columns to an already-ingested dataset), streaming uploads for very large files, CSV dialect auto-detection beyond standard comma-separation.
