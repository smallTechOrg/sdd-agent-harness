# Capability: Suggest Follow-ups

## What It Does
After each answer, proposes 2–3 smart, clickable follow-up questions derived from the question and the result schema. (Phase 2)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question text | str | the just-answered question | yes |
| result schema + key numbers | JSON | `synthesize_answer` output (bounded) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| followups | JSON (2–3 strings) | `questions.followups_json`; UI FollowupChips |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini Flash | one cheap call → 2–3 follow-ups (no full rows) | followups omitted; answer still returned |

## Business Rules
- A single, cheap LLM call (cost-aware); never sends full data rows.
- Clicking a follow-up re-asks it as a new question on the same dataset.

## Success Criteria
- [ ] After an answer, 2–3 relevant follow-ups appear and are clickable.
- [ ] Clicking a follow-up runs it as a new question and returns an answer.
