# Capability: Multi-Dataset Query

> **Status: DEFERRED — Phase 3.** Phase 1/2 query a single dataset.

## What It Does
Loads multiple datasets into one DuckDB connection so the user can compare and join across them in a single question.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_ids | list[str] | datasets sidebar multi-select | yes |
| question | str | request | yes |
| schemas | list per dataset | `Dataset.schema_json` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer / sql / result | as `analyze_question` | API response; Run row |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB (local) | attach/register multiple tables; run cross-dataset SQL | retry-on-SQL-error loop |
| Gemini | generate join/compare SQL from the combined schema | as `analyze_question` |

## Business Rules
- The combined **schema** (all selected tables + columns) is sent to Gemini; no raw rows.
- Generated SQL is DuckDB-valid and may JOIN across the registered tables.

## Success Criteria
- [ ] Selecting two datasets and asking a compare/join question returns a correct answer with the exact DuckDB SQL referencing both tables.
- [ ] The figure is reproducible by running the shown SQL.
- [ ] Test runs against the real Gemini API via `.env`.
