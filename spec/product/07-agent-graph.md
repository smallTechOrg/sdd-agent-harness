# Agent Graph

## Framework

LangGraph `StateGraph` with a ReAct loop.

## Pre-coding Answers (Required by ai-agents.md §10)

1. **What action does the LLM generate?**
   A one-line pandas expression string, e.g. `df.groupby("region")["amount"].mean()`. The expression references `df` (the session DataFrame) and any named column.

2. **Exact FINAL ANSWER string:**
   `FINAL ANSWER: <text>` — case-insensitive prefix check in `plan_action`.

3. **Recoverable vs. fatal error boundary:**
   - Recoverable: pandas raises `KeyError`, `ValueError`, bad column name — append action + error to `action_history`, route back to `plan_action` (self-correcting).
   - Fatal: DataFrame missing from store (session not found) → `handle_error` and status `failed`.

4. **Max-iterations default:** 10 (configurable via `DATACHAT_MAX_ITERATIONS`).

5. **`setup` prepares / cleans up:**
   `setup` loads the DataFrame from the module-level `_dataframe_store` into state. Cleanup happens in every terminal node (`finalize`, `force_finalize`, `handle_error`) by deleting the session's entry from `_dataframe_store` — wrapped in `finally` so no path leaks the resource.

6. **`AgentState` fields:**
   ```
   run_id: str
   session_id: str
   question: str
   df_columns: list[str]          # column names for prompt context
   action_history: list[dict]     # {"action": str, "result": str, "is_error": bool}
   iteration_count: int
   llm_response: str              # raw last LLM output
   final_answer: str | None
   tokens_input: int              # accumulated
   tokens_output: int
   error: str | None
   ```
   `action_history` is surfaced to the user in the API response as `reasoning_trace`.

7. **Action-safety boundary:**
   - Permitted operations: a frozenset of pandas method names (e.g., `mean`, `sum`, `groupby`, `value_counts`, `describe`, `head`, `filter`, `sort_values`, `nunique`, `max`, `min`, `count`) — dispatched via `getattr(df, method)(...)`.
   - The LLM output is parsed with regex to extract `method_name` and `args` — never `eval`'d raw.
   - If the parsed method is not in the allowlist, the executor returns an error result and routes back to `plan_action`.
   - The DataFrame is read-only from the agent's perspective (no assignment operations).

8. **`force_finalize` synthesises:**
   Summarises all successful results in `action_history` into a best-effort answer: "Based on the computations completed so far: [list of results]. Further analysis was not completed within the iteration limit."

## Node Definitions

| Node | Role |
|------|------|
| `setup` | Load DataFrame from store; validate session exists |
| `plan_action` | LLM call: given question + action_history, output next action or `FINAL ANSWER: <text>` |
| `execute_action` | Run pandas op via allowlist executor; append result to action_history |
| `finalize` | Write answer + trace to DB; update RunRow status = `completed`; release DataFrame |
| `force_finalize` | Synthesise best-effort answer; status = `force_completed`; release DataFrame |
| `handle_error` | Fatal error path; status = `failed`; release DataFrame |

## Edge Topology

```
START → setup
setup → plan_action              (normal)
setup → handle_error             (DataFrame missing)

plan_action → execute_action     (action detected)
plan_action → finalize           (FINAL ANSWER detected)
plan_action → force_finalize     (iteration_count >= max_iterations)
plan_action → handle_error       (LLM call failed)

execute_action → plan_action     (observe loop — always)

finalize → END
force_finalize → END
handle_error → END
```

## Stub Behaviour

The stub provider branches on prompt tags:
- `<node:plan>` in prompt → returns a fake pandas expression or `FINAL ANSWER: [stub answer]` after 1 iteration
- No tag → returns a short generic response

The stub never branches on prose keywords from the prompt body.
