# Capability: Multi-File Operations

> **Phase:** 2. This capability is a labelled stub in Phase 1 and becomes real in Phase 2.

## What It Does

Enables the user to ask questions that span two or more uploaded files by performing one of three operations: join (merge on a shared column), compare (run the same aggregation on multiple files and display side-by-side), or stack/union (concatenate rows from multiple files with the same schema).

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `question` | `string` | Chat input (same `POST /api/query/stream` endpoint) | yes |
| `file_ids` | `array[string]` (≥2 entries) | Request body | yes |
| `session_id` | `string \| null` | Request body | no |

The operation type (join, compare, stack) and join column are inferred by `plan_steps` from the question text and the file profiles. The user does not select an operation type explicitly — they ask in natural language (e.g., "join sales and customers on customer_id").

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Streaming text answer | SSE token events | Browser chat panel |
| Plotly chart | SSE chart event | Browser inline chart |
| Code steps | SSE code_step events | Browser code accordion |
| `query_runs` row | DB record with `file_ids` containing multiple IDs | SQLite |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API (`plan_steps`) | Plan a multi-file pandas operation (join/compare/stack) | Same retry policy as single-file queries |
| Sandboxed subprocess | Execute pandas merge/concat over multiple file paths | On timeout or error: retry up to 5 iterations |
| Local filesystem | Read 2+ uploaded files in the subprocess | On missing file: emit `type:"error"` naming the missing file_id |
| SQLite | Write `query_runs` row with JSON `file_ids` array | Degraded persistence if fails |

## Business Rules

- **Join:** Two files only. The join column must appear in both files. `plan_steps` infers the join column from the question or file profiles. The default join type is `inner`; the user can specify `left`, `right`, or `outer` in their question.
- **Compare:** Two or more files with compatible schemas. The agent runs the same aggregation on each file and presents results in a single chart with one series per file.
- **Stack/Union:** Two or more files with identical column names. The agent concatenates the DataFrames and resets the index. A source column (`__source_file__`) is added to identify which file each row came from.
- If the inferred operation is ambiguous (e.g., column names don't obviously match), `plan_steps` emits a `type:"clarification"` SSE event.
- The maximum number of files in a single multi-file query is 5.
- Each file in `file_ids` must have an existing `uploaded_files` row; missing IDs return HTTP 400 before the stream opens.
- The multi-file logic runs inside the same sandboxed subprocess as single-file queries — no special subprocess needed.

## Success Criteria

- [ ] Uploading two CSVs that share a column and asking "join [A] and [B] on [column]" returns a merged result with the correct number of rows (verified against a manually-computed expected join size).
- [ ] A join with no matching rows on the join column returns an empty DataFrame result and a user-readable message ("No matching rows found between the files on column X").
- [ ] A stack operation over two CSVs with the same schema returns a row count equal to the sum of both files' row counts.
- [ ] The Plotly chart for a compare operation shows one series per file.
- [ ] Providing a `file_ids` array with a non-existent ID returns HTTP 400 before the SSE stream opens.
