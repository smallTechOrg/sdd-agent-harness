# Capability: Multi-turn conversation

## What & why
A user holds a multi-turn conversation about a dataset: follow-up questions resolve against the prior turns
without restating context. Each turn is a `runs` row linked into an ordered `conversation`; on a new turn,
`run_agent(goal, conversation_id)` **reconstructs the prior turns' (goal, answer) into the initial context
window** so follow-ups resolve (context engineering — `harness/patterns/context-engineering.md` — plus
persistence; **not** a LangGraph checkpointer — see `spec/agent.md` L8 for why). Realizes the "multi-turn
conversations around the query" success criterion in `spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHILE in an existing conversation WHEN the user asks a follow-up that refers to a prior turn the system SHALL resolve it using the conversation's prior context (the earlier question and its results).
- WHEN a turn is added to a conversation the system SHALL persist it so later turns and the `/traces` view reflect the full thread in order.
- IF a follow-up is genuinely ambiguous given the prior context THEN the system SHALL ask one brief clarifying question rather than guess.

## Tools & layers touched
- tool: `get_schema`, `run_sql`, `create_chart` (as in `query-data` / `visualize-data`)
- layers: context-engineering (prior-turn reconstruction into the window) + persistence (conversations link runs into a thread). **L8 checkpointer is OFF** — the plain message-list design (no `add_messages` reducer) makes reconstruction the right fit (`spec/agent.md` L8).
- store: `conversations`, `conversation_turns` (SQLite metadata) link `runs` into an ordered thread — `harness/patterns/persistence.md`

## Evaluation
- outcome evaluation_steps:  # judged on the turn-2 answer, with turn-1 as context
  - Given turn 1 established context, does the turn-2 answer correctly use it (resolve the reference / ellipsis)?
  - Is the follow-up answer still grounded in a read-only query over the dataset?
  - Does it avoid re-asking for information already provided earlier in the conversation?
- expect_tools: [run_sql]
- forbid_tools: []

## Notes
- Eval is a **2-turn scenario**: turn 1 sets context (e.g. "total sales by region"); turn 2 is a follow-up
  that only makes sense with that context (e.g. "now just the top region, broken down by month"). The judge
  scores turn 2.
- Prior turns are seeded as (HumanMessage goal, AIMessage answer) pairs (capped to the most recent turns)
  before the new goal; the loop then runs fresh each turn. No checkpointer — reconstruction from the
  persisted `conversation_turns` is simpler and robust given the harness's plain-list `messages` design.
