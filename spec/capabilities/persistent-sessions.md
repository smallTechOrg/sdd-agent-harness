# Capability: Persistent Sessions & Conversation Memory  *(Phase 2 — STUB in Phase 1)*

## What It Does
Lets the user return across days to a session that carries conversation history, keeps datasets loaded, and resolves follow-up questions in context.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | str | sidebar resume / `POST /sessions` | yes (Phase 2) |
| question | str | question box | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| conversation turns, threaded context | JSON | `sessions`, `conversation` tables; `messages` in AgentState |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | persist/read session + conversation | inline error |
| Gemini | `plan` with prior turns threaded | retry/error per agent.md |

## Business Rules
- A follow-up referring to "that"/"the previous result" resolves against the last N conversation turns (windowed) threaded into the `plan` prompt.
- Loaded datasets remain attached to the session across restarts.

## Success Criteria
- [ ] A second question in a session uses the first question's context (not stateless) — asserted with the real LLM.
- [ ] After an app restart, the session, its dataset, and its conversation are listed and resumable.

> Phase 1: this capability is a labelled stub (sessions sidebar disabled, "coming soon"). It is wired real in Phase 2 (`sessions-backend` slice).
