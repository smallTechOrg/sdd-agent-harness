# Capability: Persistent Library, History & Memory

## What It Does
Provides a managed personal file library and a browsable question+answer history that persist across days, a running daily cost total, and conversation memory that carries context within and across sessions. (Phase 4)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| (browse) — | — | `GET /datasets`, `GET /history`, `GET /cost/daily`, `GET /conversations` | — |
| prior turns | JSON | `conversations` + prior `questions` | for memory |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| library list | JSON | UI LibrarySidebar |
| history (Q+A, plan, code, results) | JSON | UI HistoryBrowser |
| daily cost total | JSON | UI DailyCostBadge |
| conversation thread + memory | JSON | UI thread; agent `messages` state |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (local) | list/read datasets, questions, steps, cost; group conversations | local; surfaced error |
| Gemini Flash | plan informed by prior turns (memory; bounded context only) | falls back to no-memory planning |

## Business Rules
- Files and history persist across app restarts (durable SQLite + local files).
- Memory passes only prior turns/bounded results to the LLM — never full data rows.
- Deleting a dataset removes the file but retains its questions as history.

## Success Criteria
- [ ] Uploaded files and past Q&A remain after an app restart.
- [ ] The daily cost total equals the sum of today's `cost_records`.
- [ ] A follow-up question that relies on the prior turn's context is answered correctly using memory.
- [ ] A past answer can be reopened with its plan, code, and results intact.
