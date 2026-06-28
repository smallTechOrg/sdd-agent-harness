# Capability: Analyze CSV (Code-Execution Loop)

## What It Does
Answers a plain-language question about a loaded dataset by having the LangGraph agent write pandas/SQL code, run it locally on the FULL data, revise on error, and produce a small result — without ever sending bulk data to the LLM.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | `POST /analyses` body | yes |
| question | str | `POST /analyses` body | yes |
| llm_context | derived (schema + sample + prior result) | `engine.make_llm_context()` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| code | str | `runs.code` + code panel |
| result/key_numbers/summary_table | JSON | `runs.*` + answer panel |
| llm_payload | JSON | `runs.llm_payload_json` + transparency panel |
| tokens_in/out, cost_estimate | int/float | `runs.*` + cost line |
| flagged | bool | best-guess marker |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | plan / generate_code / summarize / select_chart | Retry (3×) on transient; else set `error`, run → failed |
| DuckDB/pandas (local) | Execute generated code on full data | Captured into `exec_result.error` → revise loop (cap `MAX_REVISIONS`); after cap → flagged best-guess |

## Business Rules
- The LLM only ever receives schema + ≤20 sample rows + capped aggregated results — never bulk rows (privacy boundary, enforced in `make_llm_context`).
- Generated code runs locally via a restricted `exec` (static import denylist + timeout); prefer DuckDB SQL for heavy aggregation (100MB / <30s).
- On execution error, regenerate code with the traceback up to `MAX_REVISIONS` (Phase 1: 1 retry); then return a flagged best-guess showing what was tried.
- Simple questions resolve in a single pass (no revise entered).
- Never use a hardcoded op-list — always generate executable code.

## Success Criteria
- [ ] On a ≥250k-row fixture, "total X by Y" returns the correct **full-data** aggregate (a value provably different from a 20-row-sample answer).
- [ ] `llm_payload` byte-size is bounded and contains no bulk rows (a sentinel only in row 100k never appears in any LLM payload).
- [ ] A deliberately error-prone question triggers at least one revise and still returns an answer (or a clearly flagged best-guess).
- [ ] `tokens_in`/`tokens_out`/`cost_estimate` are populated from the real Gemini usage and are > 0.
- [ ] Happy-path run completes in under ~30s.
