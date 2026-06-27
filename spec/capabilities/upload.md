# Capability: File Upload

## What It Does

Accepts a CSV or Excel file from the user, saves it to the local filesystem, extracts metadata (row count, column count, column names and types), persists an upload record to the database, and returns the metadata so the user can immediately proceed to analysis.

## Inputs

| Input | Type | Source | Required |
|-------|------|---------|----------|
| file | multipart binary | Browser file picker or drag-and-drop | Yes |
| filename | string (from multipart headers) | Browser | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| upload_id | string (UUID) | API response; stored client-side for subsequent analysis requests |
| filename | string | API response; displayed in UI |
| row_count | integer | API response; displayed in upload confirmation |
| col_count | integer | API response; displayed in upload confirmation |
| columns | list of `{ name: str, dtype: str }` | API response; used to populate analysis parameter dropdowns |
| filepath | string (absolute path) | Stored in `uploads` table only; never returned to client |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write file bytes to `data/uploads/<uuid>.<ext>` | Return HTTP 500 with `{ error: { code: "FILE_SAVE_ERROR", message: "..." } }` |
| SQLite DB | INSERT into `uploads` table | Return HTTP 500; delete the saved file if DB write fails |

## Business Rules

- Accepted MIME types / extensions: `.csv`, `.xlsx`, `.xls`. Reject all others with HTTP 422 and `{ error: { code: "UNSUPPORTED_FORMAT", message: "..." } }`.
- Maximum file size: 50 MB. Reject larger files with HTTP 413 and `{ error: { code: "FILE_TOO_LARGE", message: "..." } }`.
- Each upload receives a fresh UUID regardless of whether the same filename was uploaded before (no deduplication).
- The original filename is stored in the DB and returned to the client; the on-disk filename is `<uuid>.<ext>`.
- Row count and column count are extracted by reading the file with pandas at upload time (full parse for row count). For large files this may take a few seconds; the API call is synchronous.
- Column dtype is the pandas dtype string (e.g. `"int64"`, `"float64"`, `"object"`, `"datetime64[ns]"`).
- Files are stored at `data/uploads/` relative to the project root. The `data/` directory is created on startup if it does not exist.
- Uploaded file data is never transmitted to any external service.

## Success Criteria

- [ ] A valid CSV file under 50 MB is uploaded and returns `{ data: { upload_id, filename, row_count, col_count, columns } }` with HTTP 200, and the file exists on disk at `data/uploads/<uuid>.csv`.
- [ ] A valid `.xlsx` file is uploaded and the `columns` list includes the correct column names with accurate dtypes.
- [ ] A file over 50 MB is rejected with HTTP 413 and `error.code == "FILE_TOO_LARGE"`.
- [ ] A file with an unsupported extension (e.g. `.json`) is rejected with HTTP 422 and `error.code == "UNSUPPORTED_FORMAT"`.
- [ ] After upload, `GET /uploads` returns the new upload in the list.
- [ ] The upload record persists across server restarts (SQLite-backed).
