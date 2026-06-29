# Capability: Data Notes

> **Status: DEFERRED — Phase 3.** Phase 1/2 ship a labelled "Coming soon" notes editor.

## What It Does
Lets the user attach notes about a dataset ("revenue is in cents", "dates are UTC") that are fed into the SQL-generation prompt so the agent interprets columns correctly.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | notes editor | yes |
| text | str | notes editor | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| DataNote row | DB | `data_notes` table |
| notes context | str | injected into `generate_sql` prompt |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | store/read notes | log + proceed without notes (non-fatal) |

## Business Rules
- Notes are user-authored metadata, not raw rows — safe to send to the LLM.
- All notes for the queried dataset are included in the generation prompt.

## Success Criteria
- [ ] After adding "revenue is in cents", a "total revenue in dollars" question divides by 100 in the generated SQL.
- [ ] Notes persist across restarts.
- [ ] Test runs against the real Gemini API via `.env`.
