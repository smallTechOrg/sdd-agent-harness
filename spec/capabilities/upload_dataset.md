# Capability: Upload Dataset

## What It Does
Accepts a CSV/spreadsheet file upload, parses it locally with pandas, stores the raw file on local disk under a generated `dataset_id`, and returns the detected schema (column names + dtypes + row count) so the user can immediately start asking questions.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart file (`.csv`) | `POST /datasets` (multipart/form-data) | yes |
| filename | string | Derived from the upload | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset_id | string (uuid) | API response `data.dataset_id`; used by the ask capability |
| schema | list of `{name, dtype}` | API response `data.schema`; rendered as the column list in the UI |
| row_count | int | API response `data.row_count` |
| filename | string | API response `data.filename` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write the uploaded bytes to `data/datasets/{dataset_id}.csv` (created locally; never uploaded anywhere) | Fatal: return 500 with human copy if the write fails |
| SQLite | Insert a `DatasetRow` (metadata + schema only — NEVER raw rows) | Fatal: return 500 |

## Business Rules
- **Privacy:** the raw file is stored on the local disk only; it is never transmitted to any cloud service. Only metadata (id, filename, row count, schema) is persisted in SQLite. The raw rows are never written into any LLM-bound field.
- Parsing is done locally with pandas (`pd.read_csv`). Only `.csv` is accepted in Phase 1; other spreadsheet formats (`.xlsx`) are deferred (labelled stub in the UI is not needed — the file picker simply restricts to `.csv`).
- A file that pandas cannot parse → a 400 with human copy ("Could not read this file as CSV"), not a crash.
- File size is bounded by a configurable cap (`AGENT_MAX_UPLOAD_MB`, default 25) to keep a personal tool from being overwhelmed; over the cap → 400 with human copy.
- `dtype` reported is the pandas-detected dtype string (e.g. `int64`, `float64`, `object`, `datetime64[ns]`), normalized to friendly labels (`integer`, `decimal`, `text`, `date`) for display.

## Success Criteria
- [ ] Uploading a valid CSV returns a `dataset_id`, a `schema` listing every column with a friendly dtype, and the correct `row_count` matching `len(df)`.
- [ ] The raw file exists at `data/datasets/{dataset_id}.csv` after upload and a `DatasetRow` exists in SQLite with the schema JSON but no raw-row field.
- [ ] Uploading a non-CSV / malformed file returns a 400 with a human-readable message and writes no `DatasetRow`.
- [ ] Uploading a file larger than the cap returns a 400 with human copy.
