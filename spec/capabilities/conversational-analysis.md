# Capability: Conversational Analysis

## What It Does
Answers a natural-language question about a dataset by planning, writing pandas code, executing
it **locally against the full data**, inspecting the result, optionally refining, and returning
a plain-English answer with the generated code visible — without ever sending raw rows to the LLM.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | str | `POST /ask` | yes |
| question | str | `POST /ask` | yes |
| conversation_id | str\|null | `POST /ask` | no (null → new conversation) |
| profile + history | dict / list | server (datasets, messages) | yes (built server-side) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | str | API response + `runs.answer` + assistant `message` |
| plan | str | API response + `runs.plan` (UI collapsible) |
| code | str | API response + `runs.code` (UI collapsible) |
| result_preview | str | API response + `runs.result_preview` |
| suggestions | list | API response (2-3 follow-up chips) |
| run record | row | `runs` table |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`gemini-2.5-flash`) | plan, generate_code, inspect, answer | retry w/ backoff; then `LLM_UNAVAILABLE` → `handle_error` |
| pandas executor (`src/analysis/execute.py`) | run snippet on full DataFrame | capture error → refine loop (≤ MAX_ITERATIONS), then best-effort answer |

## Business Rules
- **Privacy invariant:** the LLM receives only schema, dtypes, stats, a ≤5-row sample, the
  question/history, generated code, errors, and a truncated aggregated result preview — never
  full rows. See [../agent.md](../agent.md) and [../architecture.md](../architecture.md).
- Generated code must run against the **full** dataset, not the sample (a sampled answer and a
  full-data answer must agree only because full data was used).
- The agent uses generated executable code, never a hardcoded op-list (anti-pattern #22).
- Refine loop is capped at `MAX_ITERATIONS` (default 3); on exhaustion the agent answers
  best-effort and flags uncertainty rather than failing.

## Success Criteria
- [ ] Asking "total revenue by region" on a multi-thousand-row CSV returns the correct
      per-region totals computed over the **full** file (verified against a pandas ground-truth
      in the test fixture).
- [ ] The response includes the exact pandas `code` and a `plan`, both shown collapsibly in UI.
- [ ] `tests/phase1/test_privacy_invariant.py` confirms no full-frame / >5-row payload is ever
      passed to the LLM client.
- [ ] A deliberately wrong first code attempt is corrected by the refine loop within the cap.
- [ ] The gate fixture is large enough that a sampled (≤5-row) computation would give an
      observably different answer than the full-data computation, proving full data was used.
