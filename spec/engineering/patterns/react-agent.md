# Pattern: ReAct Agent Loop

**Canonical home for everything about agents that act on the outside world.** When a rule elsewhere
mentions the ReAct loop, the action-safety boundary, `force_finalize`, the reasoning trace, or the
run-vs-session lifecycle, it links here. This is the only place these are defined.

**When this applies:** any agent that answers a question using tools, data (CSV, DB, APIs, files), or
search. If the agent acts on the outside world, it must run this loop — not a single-shot
"gather context → pass to LLM → return answer" pipeline. A one-shot pipeline cannot verify its inputs
or self-correct, and breaks the moment the real environment differs from the sampled context.

> **Place in the stack:** this is layer 6's **single-agent default** in
> [`../agentic-architecture.md`](../agentic-architecture.md). The other layers wire around it: context +
> memory ([`memory-and-context.md`](memory-and-context.md)), tools/MCP ([`tools-and-mcp.md`](tools-and-mcp.md)),
> retrieval ([`retrieval.md`](retrieval.md)), guardrails/HITL ([`guardrails-and-hitl.md`](guardrails-and-hitl.md)),
> durability ([`durability.md`](durability.md)), and observability/evals
> ([`observability-and-evals.md`](observability-and-evals.md)). Escalate to multiple agents only when a
> single loop can't keep the task coherent — [`multi-agent.md`](multi-agent.md) § Escalation criteria.

---

## The loop

Each iteration runs one cycle and repeats until the agent signals it is done:

**reason/plan** (LLM picks the next action, or signals done) → **act** (execute it) →
**observe** (feed the result back into the next reason step).

Reasoning and acting interleave every iteration — that is what makes it ReAct rather than planning
everything up front.

```
START → setup → plan_action ──(action)──► execute_action ──┐
                  ▲   │                                     │
                  │   ├─(finish tool called)─► finalize → END   │
                  │   └─(fatal error)─► handle_error → END  │
                  └──────────(observe: result loops back)───┘
                                                            │
   (max iterations OR repeated errors) ─► force_finalize ─► END
```

- **setup** — prepare what the agent acts on (load data, open a connection, build an index).
- **plan_action** = reason/plan · **execute_action** = act · result appended to state and looped back = observe.

---

## Mandatory mechanics

- **Termination signal.** The LLM ends the loop by calling a **structured finish tool** (e.g. a
  `finish(answer: str)` tool exposed alongside the action tools) — not a magic text prefix. The router
  checks whether the model called `finish`: if so, route to `finalize` with its typed argument;
  otherwise execute the chosen action. A structured tool call is unambiguous to parse and impossible to
  trigger accidentally from prose. Without a termination signal the loop never terminates on its own.
- **Max-iterations guard.** Configurable ceiling (`max_agent_iterations`) — **no hardcoded default;
  each project sets it explicitly** in `07-agent-graph.md` based on its task. On reaching it — or after
  repeated consecutive errors — route to **`force_finalize`**, never loop unboundedly.
- **Best-effort finalization (`force_finalize`).** Running out of iterations is not a crash:
  synthesise the best answer from `action_history` and note what's missing — never a bare "I couldn't
  do it." Reserve `handle_error` for fatal failures (data missing, LLM/network down).
- **Self-correction.** On a recoverable action error (bad query, API 4xx, missing file), append the
  action + error to history and route back to `plan_action` so the LLM sees it inline and retries.
  Hard-fail (→ `handle_error`) only on a structurally invalid action or an LLM-call failure.
- **Action-safety boundary.** See below — model-generated actions are untrusted.
- **Operator observability.** Every LLM call returns structured usage (input/output tokens, estimated
  cost) accumulated in state and persisted on the run; every node emits a structured (JSON) log bound
  to `run_id`. Token/cost per run must never be invisible.
- **User transparency.** The agent must show the user *what it is doing as it happens* — each step's
  action, its result, then the final answer — streamed or rendered from `action_history`. A glass box,
  never a spinner hiding a black box.

---

## Action-safety boundary (code-generating actions)

Treat every model-generated action as untrusted: validate it before running, and never `exec`/`eval`
raw output unsandboxed. For code-generating actions (pandas, SQL, shell) the safe-executor pattern is
**AST-parse → walk + reject dangerous nodes → compile + eval in a restricted namespace** (no
`__builtins__`, only explicitly listed names).

```python
import ast

_BLOCKED_ATTRS = frozenset({"__class__", "__dict__", "__builtins__", "to_csv", "pipe"})
_ALLOWED_NAMES = frozenset({"df", "pd", "True", "False", "None"})


def execute(df, action: str) -> tuple[str, bool]:
    try:
        tree = ast.parse(action, mode="eval")
    except SyntaxError as e:
        return f"SyntaxError: {e}", True

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "Safety error: import not allowed", True
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in _BLOCKED_ATTRS):
            return f"Safety error: attribute '{node.attr}' not allowed", True
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
            return f"Safety error: name '{node.id}' not in scope", True

    result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}, "df": df, "pd": pd})
    return str(result), False
```

**Use AST, not regex.** LLMs naturally generate chained expressions — `df.groupby("region")["sales"].sum()`,
`df.sort_values("date").head(10)`, `df["col"].value_counts().nlargest(5)`. A regex that tries to parse
call structure fails on almost every real query and fills the action history with spurious parse
errors. A frozenset allowlist of attribute names inspected during the AST walk is the correct safety
mechanism.

---

## State

`AgentState` carries the context the LLM needs on every `plan_action` call:

```python
action_history: list[dict]  # [{"description": str, "action": str, "result": str, "is_error": bool}]
iteration_count: int
last_tool_call: dict        # the model's last tool call — router checks if it's `finish`
tokens_input: int           # accumulated usage — persisted on the run record
tokens_output: int
estimated_cost_usd: float | None
```

### The `description` field is mandatory

Each `action_history` entry **must** include a `description` — a plain-English sentence the user can
read. Raw code or query strings alone are never acceptable in the user-facing trace. Structure every
`plan_action` LLM response so both are returned, and the executor stores both:

```
DESCRIPTION: <one sentence a non-technical user can understand>
ACTION: <the executable expression>
```

```python
{"description": "Grouping sales by region to find the total for each.",
 "action": "df.groupby('region')['sales'].sum()", "result": "...", "is_error": False}
```

Showing `df.groupby("region")["sales"].sum()` to a non-technical user is a UX bug — they asked a
plain-English question and expect a plain-English explanation. The golden-path smoke test
(`workflows/golden-path-smoke-test.md`) asserts `description` is present, non-empty, and not identical
to the raw `action`. The `force_finalize` summary must also use `description` fields, not raw actions.

Persist `action_history` — it is both the live user-facing trace and the audit log — with the usage fields.

---

## Resource lifecycle — run-scoped vs. session-scoped

- **Run-scoped resources** (a single LLM call's context, a short-lived connection) live in state or
  local scope and are released at the end of the node function. No module-level store needed.
- **Session-scoped resources** (DataFrames, parsed files, vector indexes, connections that span
  multiple questions on the same session) live in a module-level store keyed by **`session_id`** — not
  `run_id`. They must **not** be released in terminal nodes (`finalize`, `force_finalize`,
  `handle_error`), because the user will ask follow-up questions on the same session. Release them only
  when the session is explicitly deleted (a DELETE endpoint or LRU eviction). Releasing them
  per-question causes `SESSION_DATA_LOST` on the second question — a correctness bug, not a memory leak.

If a session-scoped resource was lost because the server restarted, the API must return a clear,
user-actionable error ("Session data is no longer available — please re-upload your file"), not a
generic 500.

---

## Spec it before coding (`spec/product/07-agent-graph.md`)

`07-agent-graph.md` must answer, before any node code is written:

1. What action the LLM generates (query, HTTP request, file path, tool call…).
2. The `finish` tool's signature (what typed answer it returns).
3. The recoverable-vs-fatal error boundary.
4. The `max_agent_iterations` value for this project (no default — set it).
5. What `setup` prepares and how it's cleaned up (run-scoped vs. session-scoped).
6. What fields `AgentState` carries for history, iteration count, and usage — and how the trace is
   surfaced to the user live.
7. The **action-safety boundary** — which operations the executor permits, how each action is
   validated, and what sandbox it runs in.
8. What `force_finalize` synthesises when iterations are exhausted.

If any are missing, raise a blocker before Phase 1.

---

## Phase 1 gate for ReAct agents

A test must exercise **at least two iterations** against the real model — one where the LLM generates an
action, one where it calls the `finish` tool. A run that finishes on the first call without executing any
action does not validate the loop; assert loosely (an action ran, then `finish`), not on exact text. A
test must also drive the loop past `max_agent_iterations` and assert a substantive best-effort answer
from `force_finalize`, not a hard failure. See `spec/engineering/phases.md` § Phase 1.
