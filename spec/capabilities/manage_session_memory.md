# Capability: Manage Session Memory

> **Status: DEFERRED — Phase 3.** Phase 1/2 answer each question independently.

## What It Does
Maintains an upload-once-ask-many session that persists across days: remembers conversation turns and keeps datasets loaded, feeding prior Q/A context into the SQL-generation prompt so follow-up questions ("and by region?") resolve correctly.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | str | client / created on first ask | yes |
| question | str | request | yes |
| prior_turns | list[{q,a}] | `Session.turns_json` | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| updated turns | JSON | `Session.turns_json` (persisted) |
| context | str | injected into `generate_sql` prompt |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | read/write session turns | log + treat as fresh session (non-fatal) |

## Business Rules
- Only prior questions and answers (which contain aggregates, not raw rows) enter the prompt — privacy boundary preserved.
- History is windowed/summarised to stay within the context budget.
- Sessions persist across app restarts.

## Success Criteria
- [ ] A follow-up question that depends on the previous turn resolves correctly using remembered context.
- [ ] Restarting the app preserves the session and its datasets.
- [ ] Test runs against the real Gemini API via `.env`.
