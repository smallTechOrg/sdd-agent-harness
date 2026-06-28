# Capability: Run History

## What It Does
Persists every agent run (question, plan, code, result preview, status, tokens/cost,
timestamps) per dataset, and (Phase 2) lets the user browse that history in the UI.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run data | fields | agent run (`finalize`) | yes |
| dataset_id | str | `GET /datasets/{id}/runs` (browse) | yes (browse) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| run record | row | `runs` table (Phase 1 — persisted) |
| run list | list | `GET /datasets/{id}/runs` → Run History panel (Phase 2 — browse) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | Write run on finalize; read for history | Write failure logged; run still returns answer |

## Business Rules
- Every run is persisted in Phase 1 (the data is captured from the first phase); the browsing
  UI and `GET /datasets/{id}/runs` endpoint land in Phase 2 (a labelled stub in Phase 1).
- History is organized per dataset and ordered by `created_at`.
- `result_preview` stored is the truncated/aggregated preview, never full rows.

## Success Criteria
- [ ] After asking a question, a `runs` row exists with question, plan, code, result_preview,
      status, and timestamps.
- [ ] (Phase 2) `GET /datasets/{id}/runs` returns prior runs for that dataset, newest first,
      and the Run History panel renders them with collapsible code/result.
- [ ] History survives a server restart (persisted in SQLite).
