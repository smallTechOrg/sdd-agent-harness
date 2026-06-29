# Capability: Cost Tracking

> **Status: DEFERRED — Phase 3.** Phase 1/2 ship a labelled "Coming soon" cost meter. (Tokens ARE persisted on the Run row from Phase 1; only the UI + warning are deferred.)

## What It Does
Tracks Gemini token usage and estimated cost per query, maintains a running session/day total, and warns the user before an expensive query.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| token usage | dict | Gemini response metadata per call | yes |
| pricing | const | configured per-token rate | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| tokens | dict (prompt, completion, est_cost) | `Run.tokens_json`; API `data.tokens`; UI cost meter |
| session_total | dict | UI cost meter |
| warning | bool | UI pre-query warning modal |

## External Calls
None beyond reading Gemini response metadata.

## Business Rules
- Per-query cost = tokens × configured rate; session/day totals accumulate.
- A pre-query estimate above a threshold triggers a warning before running.

## Success Criteria
- [ ] After a query, `data.tokens` shows prompt/completion tokens and an estimated cost; the meter increments.
- [ ] The session total equals the sum of per-query costs.
- [ ] A query estimated above the threshold surfaces a warning before running.
