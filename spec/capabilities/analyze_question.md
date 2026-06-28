# Capability: Analyze Question (core)

## What It Does
Answers a plain-language question about an uploaded CSV with a correct written answer plus key numbers, a result table, the plan it made, and the code it ran — computed locally over the full dataset, with the per-question cost shown. (Phase 1)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | `POST /questions` body | yes |
| question text | str | `POST /questions` body | yes |
| schema + sample rows | JSON | `datasets` row (extracted at upload) | yes |
| full CSV | file | `data/uploads/<id>.csv` (read locally only) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer + key_numbers | str + JSON | `questions` row, UI AnswerPanel |
| result_table | JSON (bounded) | `questions` row, UI ResultTable |
| plan | JSON | `questions` row, UI PlanView |
| steps (code + result) | rows | `analysis_steps`, UI CodeView |
| cost (tokens + USD) | row | `cost_records`, UI CostChip |
| cost_guard_warning | str\|null | `questions` row, UI banner |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini Flash | plan / generate code / synthesize answer (schema + sample rows + bounded results only) | `handle_error` → status `failed`, surfaced with steps tried |
| DuckDB/pandas (local) | run generated code over full dataset | step error stored; replan or surface |

## Business Rules
- **Privacy:** the LLM payload contains only schema, ≤ `AGENT_SAMPLE_ROWS` sample rows, the question, and prior bounded step results — never full data rows.
- **Cost guard:** ≤ `AGENT_MAX_STEPS` execute iterations; on cap hit, warn and return best-effort answer.
- **Correctness:** answers are computed over the full file, not a sample.
- Results returned to the agent/UI are bounded to `AGENT_MAX_RESULT_ROWS`.

## Success Criteria
- [ ] Upload a CSV, ask an aggregate question, get the correct number (matches a hand-computed answer over the full file).
- [ ] A question whose sampled answer differs from the full-data answer returns the full-data answer.
- [ ] The LLM payload for the question contains no full data rows (asserted in test).
- [ ] The response includes plan, per-step code, result table, and per-question token/USD cost.
- [ ] When the step cap is exceeded, `cost_guard_warning` is set and a best-effort answer is returned (no runaway looping).
