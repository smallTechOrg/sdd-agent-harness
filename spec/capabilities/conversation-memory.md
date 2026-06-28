# Capability: Conversation Memory

## What It Does
Carries prior turns of a session as context so follow-up questions resolve against earlier
answers (e.g. "now break that down by region" refers to the previous result).

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| conversation_id | str | `POST /ask` | no (null starts a new conversation) |
| prior turns | list[{role, content}] | `messages` table | yes when conversation exists |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| user turn | message row | `messages` (role=user) |
| assistant turn | message row | `messages` (role=assistant, links run_id) |
| history in state | list | `AgentState.history` → plan / generate_code context |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | Load + append messages | Fatal on read failure → `handle_error` |

## Business Rules
- `load_profile` loads prior turns into `state.history`; `plan` and `generate_code` use them so
  follow-ups are contextual.
- Only the user's own words (questions/answers) are in history — no raw data rows. History is
  windowed/truncated to stay in the context limit (see [../agent.md](../agent.md)).
- A null `conversation_id` creates a new conversation scoped to the dataset.

## Success Criteria
- [ ] Asking "total revenue" then "now break that down by region" in the same conversation
      produces a region breakdown of revenue (the follow-up used prior context).
- [ ] Both turns are persisted as `messages` rows and reloaded after a server restart.
- [ ] A new `conversation_id=null` request starts a fresh thread with no prior context.
