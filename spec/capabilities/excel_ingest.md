# Capability: Excel Ingest

> **Status: DEFERRED — Phase 3.** Phase 1/2 accept CSV only; the UI labels Excel "Coming soon".

## What It Does
Accepts `.xlsx` uploads, reads them (via `openpyxl`), and ingests the chosen sheet into a local DuckDB file exactly like CSV ingest.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | .xlsx upload | `POST /datasets` | yes |
| sheet | str | optional sheet name (default first) | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Dataset | DB + DuckDB file | same as CSV ingest |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| openpyxl | parse workbook/sheet | 400 with a clear message |
| DuckDB (local) | load sheet rows into a table | 500 on ingest failure |

## Business Rules
- Adds `openpyxl>=3.1` to dependencies.
- Once ingested, an Excel dataset is indistinguishable downstream from a CSV dataset (same schema/profile/query path).

## Success Criteria
- [ ] Uploading an `.xlsx` produces a Dataset with the correct schema and row count.
- [ ] A question over the Excel dataset returns a correct answer with exact DuckDB SQL.
