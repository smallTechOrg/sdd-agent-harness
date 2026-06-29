# Capability: Summarize Result

> **Status: DEFERRED — Phase 2.** Phase 1 ships a labelled "Coming soon" rich summary-table area (the basic aggregate result table IS shown in Phase 1).

## What It Does
Formats the answer's result set into a clean summary table payload (column headers, typed/rounded values, ordering) for richer display than the raw aggregate rows.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| result | list[dict] | `analyze_question` result rows | yes |
| schema | list[{name,type}] | dataset schema | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| summary_table | dict (columns, rows, formatting) | API `data.summary_table`; UI summary table |

## External Calls
None — pure formatting over the aggregate result.

## Business Rules
- Operates only on the aggregate result rows (no raw rows).
- Deterministic formatting (number rounding, header casing) — no LLM needed.

## Success Criteria
- [ ] A multi-row aggregate result renders as a formatted table with typed/rounded values.
- [ ] Formatting matches the result values exactly (no altered numbers).
