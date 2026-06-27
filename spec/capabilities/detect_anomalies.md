# Capability: Detect Anomalies & Patterns

> **Phase 3.** Phase 1 ships this as a clearly-labelled non-functional UI stub.

## What It Does
Runs local statistical checks (outliers, nulls, distribution skew, simple correlations) over the dataset with pandas, then asks Gemini to turn those **derived findings** into a short, prioritized plain-English list of notable patterns and anomalies — raw rows never leave the machine.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string (uuid) | `POST /datasets/{dataset_id}/insights` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| findings | list of `{title, detail, severity}` | API response `data.findings`; rendered as an insights list |
| status | string (`completed` \| `failed`) | API response `data.status` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local pandas | Compute outlier counts (IQR/z-score), null rates, skew, top correlations — all locally | Fatal: human copy |
| Gemini (`gemini-2.5-flash`) | One call: given the derived statistical findings (no raw rows), rank and phrase them as plain-English insights | Fatal for the request: human copy, status `failed` |

## Business Rules
- **Privacy:** the statistical findings sent to Gemini are derived aggregates (counts, rates, coefficients, column names) — never raw rows. Gemini only ranks and phrases them.
- Detection logic is deterministic local pandas; the LLM never invents findings not present in the computed statistics. The system prompt forbids adding findings beyond the supplied list.
- Findings are capped (e.g. top 8 by severity) to keep the payload and prompt small.

## Success Criteria
- [ ] A dataset with an injected extreme outlier yields a finding that names the affected column with `severity` high.
- [ ] A dataset with a high-null column yields a null-rate finding for that column.
- [ ] The Gemini prompt contains only derived statistics, no raw rows (asserted in test).
- [ ] Every finding the LLM returns maps to a column/statistic that was actually supplied (no fabricated columns).
