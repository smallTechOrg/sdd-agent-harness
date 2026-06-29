# Capability: Audit Trail

> **Status: DEFERRED — Phase 3.** Phase 1/2 ship a labelled "Coming soon" history browser. (Runs ARE persisted from Phase 1; only browsing the history is deferred.)

## What It Does
Persists and lets the user browse the full run history (question, generated SQL, result, status, tokens, timestamp) for a dataset.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | history view | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| runs | list[Run] | API `GET /datasets/{id}/runs`; UI history browser |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | read `runs` for dataset | surfaced error (500) |

## Business Rules
- Every analysis writes a Run row (already true from Phase 1) — the trail is append-only, never deleted.
- History shows the exact SQL behind each past answer for reproducibility.

## Success Criteria
- [ ] `GET /datasets/{id}/runs` returns past runs with question, SQL, result, timestamp.
- [ ] The history browser lists them and shows each run's exact SQL.
