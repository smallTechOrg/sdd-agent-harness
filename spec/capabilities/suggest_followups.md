# Capability: Suggest Follow-ups

> **Status: DEFERRED — Phase 2.** Phase 1 ships labelled "Coming soon" follow-up chips.

## What It Does
After each answer, suggests 2–3 relevant follow-up questions based on the schema and the just-returned result (not raw data).

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | str | the run's question | yes |
| schema | list[{name,type}] | dataset schema | yes |
| result | list[dict] | answer result rows | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| followups | list[str] (2–3) | API `data.followups`; UI follow-up chips |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini `gemini-3.1-pro` | propose follow-ups from schema + result | log + return `followups: null` (non-fatal) |

## Business Rules
- Prompt receives schema + aggregate result only — no raw rows.
- Clicking a chip submits it as the next question (UI).

## Success Criteria
- [ ] After an answer, `data.followups` has 2–3 plausible questions grounded in the dataset columns.
- [ ] Clicking a chip submits it and produces a new answer.
- [ ] Test runs against the real Gemini API via `.env`.
