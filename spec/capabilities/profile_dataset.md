# Capability: Profile Dataset

> **Status: DEFERRED — Phase 2.** Phase 1 ships a labelled "Coming soon" profile panel.

## What It Does
On upload, auto-profiles a dataset by computing per-column statistics locally in DuckDB (type, null count, distinct count, min/max for numerics) and stores them for display and prompt context.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | upload flow | yes |
| dataset_path | str | `Dataset.duckdb_path` | yes |
| schema | list[{name,type}] | `Dataset.schema_json` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| profile | list[dict] | `Dataset.profile_json`; API `data.profile`; UI profile panel |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB (local) | aggregate stats per column | log + continue with partial profile (non-fatal) |

## Business Rules
- Computed entirely in DuckDB; only aggregate stats (never raw rows) may later feed a prompt.
- Runs once at ingest; cached on the `Dataset`.

## Success Criteria
- [ ] After upload, `data.profile` contains one entry per column with null/distinct counts and (for numerics) min/max.
- [ ] Stats match a direct DuckDB query on the dataset.
- [ ] The profile panel renders the stats in the UI.
