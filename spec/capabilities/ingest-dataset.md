# Capability: Ingest Dataset

## What It Does
Loads an uploaded CSV/Excel file into the local DuckDB analysis engine (and a parquet copy), and returns its schema + a small sample + row count.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart upload (CSV/.xlsx) | Browser upload zone (`POST /datasets`) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset_id, name, schema, sample (≤20 rows), row_count | JSON | API response + `datasets` row + DuckDB table `ds_{id}` + parquet |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB (local) | Create table from file; extract schema/sample/count | 400 `BAD_FILE` / 500 `INGEST_ERROR` |
| Filesystem | Write upload + parquet under `data/` | 500 `INGEST_ERROR` |

## Business Rules
- Files up to ~100MB; larger → 413 `TOO_LARGE`.
- The returned `sample` IS the same sample the LLM may later see (transparency by construction) — capped at 20 rows.
- No bulk rows are returned to the client or LLM — only schema + sample + count.
- Phase 1: profile-lite only (schema + sample + count). Full column profile (ranges/missing/cardinality) is Phase 2.

## Success Criteria
- [ ] Uploading a ≥250k-row CSV creates a DuckDB table and a `datasets` row, and returns the correct `row_count`.
- [ ] The response `sample` has ≤20 rows and the schema dtypes match the file.
- [ ] An unsupported/corrupt file returns 400 `BAD_FILE`, not a 500/crash.
