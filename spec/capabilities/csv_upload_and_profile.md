# Capability: CSV Upload and Profile

## What It Does

Accepts a CSV file uploaded by the user, saves it to the local filesystem, runs a pandas-based profiler, and immediately returns the column names, dtypes, null counts, row count, and 3 sample values per column.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `file` | `UploadFile` (multipart) | Browser file picker → `POST /api/files/upload` | yes |
| `session_id` | `string` | Request form field | no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `file_id` | `string` (UUID4) | JSON response body; stored in browser state for subsequent queries |
| `profile` | `FileProfile` JSON object | JSON response body; rendered as a profile card in the chat panel |
| Filesystem file | Raw bytes at `uploads/<file_id>.csv` | Local `uploads/` directory |
| `uploaded_files` row | DB record | SQLite `uploaded_files` table |

`FileProfile` shape: `{columns: [{name, dtype, null_count, sample_values: [3 items]}], row_count, column_count, file_size_bytes, profiled_at}`.

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write file to `uploads/<file_id>.csv` | Return HTTP 500; do not write DB row |
| SQLite | `INSERT INTO uploaded_files` | Return HTTP 500; delete the written file |
| pandas | `pd.read_csv()` + dtype introspection | Return HTTP 500 with message "Could not parse file as CSV" |

## Business Rules

- Accepted file extensions in Phase 1: `.csv` only. (`.xlsx` added in Phase 3.)
- Maximum file size: 100 MB. Files larger than this are rejected with HTTP 413 before the file is written.
- The profiler reads the entire file to compute accurate null counts and row count. It does not sample.
- `sample_values` contains at most 3 non-null values from the first 100 rows. If a column has fewer than 3 non-null values in the first 100 rows, fewer sample values are returned.
- `dtype` is the pandas dtype string (e.g., `"int64"`, `"float64"`, `"object"`, `"datetime64[ns]"`).
- The profile is computed synchronously in the upload endpoint (not deferred to a background task). For large files this may take a few seconds — the frontend shows a spinner during upload.
- `file_id` is a UUID4 generated at upload time. It is never reused or recycled.
- If the same filename is uploaded twice, two separate `uploaded_files` rows are created with different `file_id` values. No deduplication.

## Success Criteria

- [ ] Uploading a 1,000-row CSV returns a `profile.columns` list matching the actual column count of the file.
- [ ] `profile.row_count` equals the actual number of data rows in the uploaded file (excluding the header).
- [ ] `profile.columns[i].null_count` equals the actual number of null values in that column (verified against a CSV with known nulls).
- [ ] A file exceeding 100 MB is rejected with HTTP 413 and nothing is written to the filesystem or DB.
- [ ] A file with a `.txt` extension is rejected with HTTP 400.
- [ ] The uploaded file is readable from `uploads/<file_id>.csv` after a successful upload.
- [ ] A successful upload returns HTTP 200 within 10 seconds for a 10 MB CSV.
