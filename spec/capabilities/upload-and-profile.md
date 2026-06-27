# Capability: Upload and Profile

## What It Does
Accepts a CSV or `.xlsx` upload, stores it locally, and returns its detected schema (column names + inferred types) and row count — with no LLM call.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart file (CSV or .xlsx) | user upload via `POST /datasets` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset_id | string (uuid) | API response; used by later questions |
| schema | object `{columns:[{name,dtype}]}` | API response → UI sidebar |
| row_count | integer | API response → UI sidebar |
| stored file | file on disk | `./data/uploads/<dataset_id>.<ext>` (raw rows stay here) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | write the uploaded file | return 400/500 with a clear message |
| pandas | read file + infer dtypes + count rows | return 400 `BAD_UPLOAD` if unreadable/empty |

## Business Rules
- Only `csv` and `xlsx` accepted; anything else → 400.
- `.xlsx`: first sheet only, header assumed in row 1.
- Type inference maps pandas dtypes to a small set: `number`, `string`, `date`, `boolean`.
- **No LLM call** — profiling is fully local. Raw rows are never read into any prompt.

## Success Criteria
- [ ] Uploading a valid CSV returns a dataset_id, the correct column list with sensible types, and the exact row count.
- [ ] Uploading a valid `.xlsx` works identically.
- [ ] Uploading a `.txt` or corrupt file returns a 400 with a readable message, not a 500.
- [ ] The raw file exists under `./data/uploads/` and no row data is written to the DB.
