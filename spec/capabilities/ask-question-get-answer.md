# Capability: Ask a Question, Get an Answer

## What It Does
Takes a plain-language question about an uploaded dataset, plans an aggregation via the LLM, computes it locally over the raw file, and returns a plain-language answer grounded in that local result — with the privacy boundary enforced (only schema + aggregates reach the LLM).

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string | client | yes |
| question | string | user chat input | yes |
| conversation_id | string | client (after turn 1) | no |
| recent history | list of turns | server-reconstructed from `Message` rows | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | string | API response → chat thread |
| conversation_id | string | API response (new or echoed) |
| persisted messages | Message rows | SQLite |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`plan_aggregation`) | question + **schema + history** → aggregation plan | 502 `LLM_ERROR` (Phase 1); retry in Phase 5 |
| pandas (`run_local_aggregation`) | execute plan locally over raw file | 500 `INTERNAL` (Phase 1); plan-repair in Phase 5 |
| Gemini (`compose_answer`) | **aggregate table** → plain-language answer | 502 `LLM_ERROR` |

## Business Rules
- **Privacy boundary:** the LLM only ever receives schema, recent chat turns, the question, and the small aggregate table — **never raw rows**.
- Aggregate tables sent to the compose LLM are capped at 50 rows to bound tokens (cost-conscious).
- Recent conversation history (last 6 turns) is passed to the planner so simple follow-ups resolve. (Deeper memory is Phase 2.)
- A question referencing a non-existent column fails cleanly in Phase 1 (error bubble); Phase 5 repairs it.

## Success Criteria
- [ ] "What were total sales by region?" returns a correct answer matching a locally-computed groupby-sum.
- [ ] A follow-up "break that down by month" uses the prior turn's context to produce a monthly breakdown.
- [ ] A test inspecting the exact LLM-bound payloads confirms **no raw data row** appears in any prompt.
- [ ] The gate fixture is large enough (≥ 500 rows, ≥ 12 group keys) that a sampled answer would differ from the full-data answer, proving the aggregation ran over the full file.
