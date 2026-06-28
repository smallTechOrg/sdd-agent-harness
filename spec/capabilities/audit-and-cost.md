# Capability: Per-Dataset Audit History & Cost Tracking

## What It Does
Persists every run (question, plan, exact code, results, per-step trail, tokens, cost, timestamps) to SQLite so the user can browse the full history per dataset, and shows per-question cost + tokens plus a running daily total.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run + steps | records | the answer/stream capabilities | yes |
| token usage | int counts | Gemini response metadata | yes |
| cost rates | float | settings (`AGENT_COST_PER_1K_*`) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| run history list | JSON | `GET /datasets/{id}/runs` + history drawer |
| full run detail | JSON | `GET /runs/{id}` |
| per-question cost/tokens | JSON | answer card cost meter |
| daily total | JSON | `GET /usage/today` + top-right meter |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | write/read runs + run_steps | run still completes; logging warns if persistence fails |

## Business Rules
- Cost = (prompt_tokens/1000 * rate_in) + (completion_tokens/1000 * rate_out), summed across the run's LLM calls.
- Daily total aggregates all runs created today.
- History is scoped and browsable per dataset.
- Persisted fields contain only schema/aggregates — never raw rows.

## Success Criteria
- [ ] Every completed and failed run appears in that dataset's history with question, status, step count, and cost.
- [ ] Opening a past run shows its plan, every step, exact code, chart, and table.
- [ ] The per-question cost/tokens and the running daily total display and update after each question.
