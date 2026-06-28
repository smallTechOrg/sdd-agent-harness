# Capability: Profile Dataset

## What It Does
On upload, auto-profiles a file locally: per-column type, ranges (min/max), null counts, distinct counts, and obvious data-quality flags — shown in the dataset bar. (Phase 2)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | upload flow | yes |
| full CSV | file | `data/uploads/<id>.csv` (local only) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| profile | JSON | `dataset_profiles` row; `GET /datasets/{id}/profile`; UI ProfilePanel |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB (local) | aggregate per-column stats over full data | profile marked partial; upload still succeeds |

## Business Rules
- Computed entirely locally (no LLM, no full rows leave the machine).
- Profiling never blocks upload success; it can complete asynchronously.

## Success Criteria
- [ ] After upload, the profile shows correct type, min/max, null count, and distinct count per column for a known fixture.
- [ ] At least one data-quality flag (e.g. high-null column, constant column) is raised when present.
