# Capability: Answer a Question with Multi-Step Reasoning

## What It Does
Takes a plain-language question about the loaded dataset and answers it via a bounded LangGraph loop — plan → write pandas code → run it server-side on the full data → inspect → refine — returning prose, an interactive chart, a results table, and the exact code, while keeping raw rows off the LLM.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | string | `POST /datasets/{id}/ask` | yes |
| dataset_id | string | path | yes |
| conversation history | list of turns | seeded from prior runs (session memory) | no |
| profile | JSON | `datasets.profile_json` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| prose answer | string | SSE `answer` event + `runs.prose` |
| chart spec | JSON | answer card (Recharts) + `runs.chart_json` |
| results table | JSON (aggregate) | answer card + `runs.table_json` |
| exact code | string | collapsible "Show code" + `runs.final_code` |
| suggested follow-ups | list[string] | answer card |
| Run + RunStep records | rows | SQLite |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`gemini-2.5-flash`) | plan / generate / inspect / finalize | retry x2, then run marked failed (partial steps kept) |
| pandas executor (sandboxed) | run generated code on full DataFrame | error fed to `inspect` to drive a refine (not fatal) |

## Business Rules
- Bounded to `AGENT_MAX_STEPS` (default 6) loop iterations.
- Clarify-first: if the question is ambiguous, return a clarifying question instead of an answer.
- Flag uncertainty (e.g. on hitting the step limit) in the answer.
- Code runs against the FULL dataset — never a sample.
- Only schema + computed aggregates/results reach the LLM (privacy boundary).

## Success Criteria
- [ ] A typical question returns prose + chart + table + exact code in ~30s.
- [ ] The exact pandas code that produced the answer is shown collapsibly and matches what ran.
- [ ] An aggregate over a ≥200k-row file matches a full-data computation (not a sample) — verified by `test_full_dataset_not_sampled`.
- [ ] No raw cell value appears in any outbound LLM payload — verified by `test_privacy_boundary`.
- [ ] An ambiguous question yields a clarifying question, not a guessed answer.
