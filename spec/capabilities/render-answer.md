# Capability: Render Answer

## What It Does
Presents a completed analysis in the browser: prose + key numbers, an interactive Plotly chart, the summary table, the exact generated code, the exact LLM payload, and the per-question cost — plus labelled stubs for deferred features.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| analysis result | JSON | `POST /analyses` response | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| rendered answer panel, chart, table, code panel, transparency panel, cost line | DOM | Browser (`/app/`) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Backend API | `POST /analyses`, `GET /analyses/{id}` (progress) | Inline error state; staged progress stepper |

## Business Rules
- The chart is rendered from `chart_spec` via `react-plotly.js`, client-only (static-export safe), interactive (zoom/hover/filter).
- The transparency panel shows `llm_payload` verbatim — proving the privacy boundary to the user.
- The code panel shows `code` verbatim and is copyable.
- A flagged best-guess is visually distinct from a confident answer.
- All deferred features appear as clearly-labelled, disabled "coming soon" stubs.

## Success Criteria
- [ ] After an analysis, the chart renders and is interactive (Playwright asserts a Plotly node + hover).
- [ ] The code panel reveals the exact code; the transparency panel reveals the LLM payload.
- [ ] The cost line shows tokens in/out + a dollar estimate.
- [ ] Every stub region is visibly labelled "coming soon" and does not error when clicked (Playwright asserts no crash).
