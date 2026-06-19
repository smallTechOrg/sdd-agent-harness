# Capability: Multi-Turn Conversation

## What & why

After an initial query the user can ask follow-up questions that refine, filter, or extend the previous result — "Now filter for Europe only", "Break that down by month", "What's the average of the second column?" — without re-stating which dataset or what was asked before. The agent maintains conversation context across turns using the LangGraph short-term memory checkpointer (`thread_id` keyed to the session). This serves the third success criterion in `spec/product.md`: a follow-up question correctly applies its constraint relative to the prior turn.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN a user sends a follow-up question that implicitly references the prior turn (e.g. uses "it", "that", "the same dataset", or adds a filter) the system SHALL incorporate the prior context and produce a SQL query that correctly applies the new constraint without requiring the user to restate the dataset name or original question.
- WHEN a conversation thread is resumed with the same `thread_id` the system SHALL have access to all prior messages in that thread and use them to resolve ambiguous references in the new question.
- WHEN the user explicitly changes topic to a different dataset in the same thread the system SHALL detect the topic shift (via `list_datasets` / `get_dataset_schema`) and query the newly referenced dataset rather than the one from prior turns.
- IF the `thread_id` is absent or new the system SHALL start a fresh conversation with no assumed context from prior threads.
- WHEN a follow-up question cannot be resolved even with prior context (e.g. references a column that does not exist in any dataset) the system SHALL ask a clarifying question rather than fabricating an answer.

## Tools & layers touched

- tool: `list_datasets` (in-process @tool — re-orient after a topic shift)
- tool: `get_dataset_schema` (in-process @tool — confirm schema after topic shift)
- tool: `execute_sql` (in-process @tool — run the context-aware SQL)
- tool: `finish` (in-process @tool — emit the final answer)
- Short-term memory: LangGraph `AsyncSqliteSaver` checkpointer keyed to `thread_id`; `POST /runs` accepts `thread_id` in the request body — `harness/patterns/memory.md`
- Interface: `POST /runs` body extended with optional `thread_id: str` field — `harness/patterns/interface.md`

## Evaluation

- outcome evaluation_steps:
  - Does the follow-up answer correctly apply the constraint from the follow-up question (e.g. filter, grouping, date range) relative to what was established in the prior turn?
  - Does the SQL query in the trajectory reflect the combined intent of the full conversation, not just the last message in isolation?
  - Is the answer free of invented column names or values?
- expect_tools: [execute_sql, finish]
- forbid_tools: []

## Notes

- The `thread_id` is created client-side at session start (uuid4) and sent with every message in that chat session. The checkpointer stores the full `AgentState` per thread so the graph resumes where it left off.
- The client (Next.js UI) stores the `thread_id` in local component state for the duration of the browser session; it is not persisted to localStorage (cross-session persistence is out of scope).
- Short-term memory is ON; long-term / cross-run memory is OFF (see `spec/agent.md`). Uploaded datasets do not persist across browser sessions.
- Context window management: the checkpointer replays the full message list; for very long threads the context engineering layer (`L2`) trims old tool-result messages to stay within the token budget while keeping human/assistant turns.
- Out of scope: branching conversation history ("go back to my earlier question"), conversation export, or sharing a thread between users.
