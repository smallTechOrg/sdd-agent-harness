# Capability: Dataset Upload

## What It Does

Accepts a CSV or JSON file from the user, stores it locally, infers its schema (column names and types), and registers it in the active session so it is available for querying.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| File | Binary (multipart/form-data) | Web UI upload form | Yes |
| File name | String | HTTP header / form field | Yes |
| Session ID | String (cookie) | Browser session cookie | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Dataset ID | UUID string | Session store; returned in API response |
| Schema summary | Object: `{ columns: [{name, type}], row_count, size_bytes }` | Session store; returned in API response |
| Stored file | Binary file | Local dataset store (filesystem) |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write uploaded file to dataset storage directory | Return HTTP 500; do not create session entry |

## Business Rules

- Accepted formats: `.csv` and `.json` only; any other extension or MIME type is rejected with a 400 error.
- Maximum file size: 50 MB. Files exceeding this limit are rejected before any bytes are written to disk.
- The schema is inferred automatically from the file content; the user does not provide column types.
- For JSON files, the top-level value must be an array of objects; any other structure is rejected with a descriptive error message.
- A single session may hold multiple datasets; each is stored and tracked independently.
- Dataset names within a session must be unique; uploading a second file with the same name overwrites the first. The existing `dataset_id` (UUID) is retained — only `schema` (columns), `row_count`, `size_bytes`, and `uploaded_at` are updated. Retaining the `dataset_id` preserves any in-flight session references that cache the identifier.
- The stored file is never sent to any external service; only the inferred schema is used in downstream LLM calls.

## Success Criteria

- [ ] Uploading a valid CSV file returns HTTP 200 with a dataset ID and a schema object containing at least one column entry within 5 seconds for a 50 MB file.
- [ ] Uploading a valid JSON array-of-objects file returns HTTP 200 with a correct schema within 5 seconds.
- [ ] Uploading a file larger than 50 MB returns HTTP 400 before writing anything to disk.
- [ ] Uploading a file with an unsupported extension (e.g. `.xlsx`) returns HTTP 400 with an error message naming the accepted formats.
- [ ] After upload, the dataset ID appears in the session's dataset list on a subsequent GET to the session endpoint.
- [ ] The stored file is present on the local filesystem at the path recorded in the session store.
- [ ] Uploading a CSV file with no header row, or a CSV file that cannot be parsed, returns an error response (HTTP 400) and no DatasetMeta is created in the session store.
