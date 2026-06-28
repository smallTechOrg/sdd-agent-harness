# Capability: Profile Dataset on Upload

## What It Does
On upload of a single CSV/Excel file, loads it server-side and auto-generates a schema profile — columns, dtypes, value ranges, and obvious data-quality issues — without sending any raw rows to the LLM.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | CSV/Excel upload | `POST /datasets` multipart | yes |
| name | string | request (optional) | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Dataset record | row | SQLite `datasets` |
| profile | JSON (columns, dtypes, ranges, quality_flags) | API response + profile panel |
| loaded DataFrame | in-memory | `DatasetStore` cache |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| pandas/openpyxl | read file into DataFrame | 400 if malformed/too large |

## Business Rules
- Accept CSV and `.xlsx`; reject other types and files over the ~100MB limit.
- Profile contains schema + aggregates only — never raw rows.
- Quality flags surface unparseable dates, high-null columns, duplicate rows, and mixed-type columns.

## Success Criteria
- [ ] A ~100MB CSV uploads and profiles within a few seconds and returns column/dtype/range/quality data.
- [ ] The profile JSON contains no raw cell value from the data body.
- [ ] An invalid file returns a 400 with a clear reason.
