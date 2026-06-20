# Pattern: the ReAct Deep-Agent loop (LangGraph)

The agent's control loop. **Generate this fresh at build time**, pinning the *current* `langgraph` /
`langchain` (check the latest first — a guessed/old version 404s). The code below is proven working.

## Shape
Nodes: `agent → (tools → agent)* → finalize`. The model is bound to the tools; if it emits tool calls
they run and the loop continues; when it calls `finish` (or hits the iteration cap) it finalizes.

## Code — `agent/state.py`
```python
from langchain_core.messages import BaseMessage
from typing import TypedDict

class AgentState(TypedDict):
    messages: list[BaseMessage]    # see the WARNING below — NO add_messages reducer
    iterations: int
    answer: str | None
    run_id: str
```

> **⚠️ `messages` must be a PLAIN `list[BaseMessage]` — do NOT use `Annotated[list, add_messages]`.**
> The nodes in `graph.py` return the **full updated list themselves** (`state["messages"] + [resp]`), so a
> LangGraph `add_messages` reducer would **append on top of an already-complete list and double-append**,
> corrupting the transcript (and the `/traces` history). Keep `AgentState` a plain `TypedDict`; the nodes own
> the merge. This is the single gap most likely to silently break a build — do not "helpfully" add a reducer.
>
> **Multi-turn consequence (no reducer ⇒ the runner owns history, not the channel).** With a checkpointer,
> resuming a `thread_id` reloads the saved `messages` channel — but because there is no reducer, the fresh
> `state["messages"]` the runner seeds **overwrites** that replay rather than appending. So on a follow-up
> turn the runner MUST read the prior messages out of the checkpoint itself and build the seed as
> `prior_messages (stale SystemMessage stripped) + [fresh SystemMessage] + [new HumanMessage]`
> (`runner.py` below, `patterns/memory.md`). The plain-list rule and the checkpointer coexist: the channel
> persists the transcript, the runner composes each turn's seed. Never `compile(checkpointer=...)` a graph
> `build_graph` already returned — pass the saver *into* `build_graph` (one compile).

## Code — `agent/graph.py`
```python
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from .config import get_settings
from .observability import span          # patterns/observability-and-evals.md
from .state import AgentState            # TypedDict: messages, iterations, answer, run_id
from .tools import FINISH, TOOL_MAP, TOOLS   # patterns/tools-and-mcp.md

def build_graph(model, checkpointer=None):
    # checkpointer is OPTIONAL: pass an AsyncSqliteSaver (patterns/memory.md) to turn on short-term
    # (multi-turn) memory; leave None for a single-shot run. build_graph owns the ONE .compile() — never
    # compile its return value again (that double-compiles). See the checkpointer note under the loop.
    bound = model.bind_tools(TOOLS)
    settings = get_settings()

    async def agent_node(state):
        async with span(state["run_id"], f"chat {settings.llm_model}", "LLM") as sp:
            resp = await bound.ainvoke(state["messages"])
            if (u := getattr(resp, "usage_metadata", None)):
                # usage_metadata may be a TypedDict (dict) or an object — guard both
                sp["tokens"] = {
                    "input":  u.get("input_tokens", 0) if isinstance(u, dict) else getattr(u, "input_tokens", 0),
                    "output": u.get("output_tokens", 0) if isinstance(u, dict) else getattr(u, "output_tokens", 0),
                }
        return {"messages": state["messages"] + [resp], "iterations": state["iterations"] + 1}

    async def tools_node(state):
        out = []
        for tc in state["messages"][-1].tool_calls:
            if tc["name"] == FINISH:
                continue
            tool = TOOL_MAP.get(tc["name"])
            async with span(state["run_id"], f"execute_tool.{tc['name']}", "TOOL", args=tc["args"]) as sp:
                # GRACEFUL DEGRADATION: a tool failure must NOT crash the loop — record it, hand the model an
                # error ToolMessage, and let it recover (retry, route around, or finish with what it has).
                try:
                    if not tool:
                        result = f"unknown tool: {tc['name']}"
                    elif getattr(tool, "coroutine", None) is not None:
                        # ASYNC tool (any I/O tool — web search, DB, HTTP API): await ainvoke. Calling .invoke
                        # on an async StructuredTool raises NotImplementedError, which the except below would
                        # swallow as a tool failure every iteration → a sourceless force-finalized answer.
                        result = await tool.ainvoke(tc["args"])
                    else:
                        result = tool.invoke(tc["args"])      # sync tool (pure-compute, no I/O)
                except Exception as exc:
                    result = f"tool '{tc['name']}' failed: {type(exc).__name__}: {exc}"
                    sp["error"] = result                       # surfaced in /traces in red
                sp["result_preview"] = str(result)[:300]
            out.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": state["messages"] + out}

    async def finalize_node(state):
        msgs = state["messages"]
        answer = None
        # 1. finish tool's answer — scan backwards (hit cap = AIMessage with tool_calls, not finish)
        for m in reversed(msgs):
            for tc in getattr(m, "tool_calls", None) or []:
                if tc["name"] == FINISH and tc["args"].get("answer"):
                    answer = tc["args"]["answer"]
                    break
            if answer:
                break
        # 2. last AIMessage text — coerce structured content (list-of-parts) to str
        if not answer:
            raw = getattr(msgs[-1], "content", None)
            if isinstance(raw, list):
                raw = "\n".join(p["text"] for p in raw if isinstance(p, dict) and p.get("type") == "text") or None
            answer = raw or None
        # 3. last resort: most recent tool result (best-effort answer, never blank)
        if not answer:
            last_tool = next((m for m in reversed(msgs) if isinstance(m, ToolMessage) and m.content), None)
            if last_tool:
                answer = "Ran out of steps — here is what I gathered:\n\n" + str(last_tool.content)
        return {"answer": answer or "(no answer produced)"}

    def route(state):
        if state["iterations"] >= settings.max_iterations:
            return "finalize"                      # force_finalize
        tcs = getattr(state["messages"][-1], "tool_calls", None)
        if tcs:
            return "finalize" if any(t["name"] == FINISH for t in tcs) else "tools"
        return "finalize"

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node); g.add_node("tools", tools_node); g.add_node("finalize", finalize_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", "finalize": "finalize"})
    g.add_edge("tools", "agent"); g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)   # None = no persistence; a saver = short-term memory
```

## Mandatory mechanics (do not omit)
- **Termination** — the `finish` tool carries the final answer.
- **Max-iterations guard + force_finalize** — never loop forever; on cap, finalize a *best-effort* answer
  (the multi-layer fallback above — never a blank `"(no answer produced)"`). Size `max_iterations` to the
  realistic **worst-case tool depth** (e.g. discovery + one call per resource + finish), not the happy path:
  a cap that's too tight turns complex requests into silent empty answers.
- **Multi-turn (when checkpointed)** — on resume the checkpointer returns a raw **dict** (read
  `cp["channel_values"]["messages"]`, not an attribute). Strip the stored `SystemMessage` and prepend a
  freshly-built one **each turn** so the *current* context (active resource, rules) applies — never replay a
  stale system prompt from when the thread started. → `patterns/memory.md`.
- **Observability** — every LLM + tool step is wrapped in a span → `patterns/observability-and-evals.md`.
- **Deep-Agent pillars** — add a `write_todos` planning tool; sub-agents + scratchpad memory earn their place.

## Gate (the test that proves it — run it, don't trust it)
Inject a scripted fake model (no key) that returns a tool call then a `finish`; assert the loop ran ≥2
iterations, the tool span exists, and a runaway model force-finalizes instead of looping. → `workflows/gates.md`.
```python
class FakeModel:
    def __init__(self, scripted): self.s = list(scripted); self.i = 0
    def bind_tools(self, tools): return self
    async def ainvoke(self, msgs):
        m = self.s[min(self.i, len(self.s) - 1)]; self.i += 1; return m
# Replace "<your_tool>" with one of YOUR agent's tool names (from patterns/tools-and-mcp.md) — it is a
# placeholder, NOT a required tool:
# scripted = [AIMessage(content="", tool_calls=[{"name":"<your_tool>","args":{...},"id":"a"}]),
#             AIMessage(content="", tool_calls=[{"name":"finish","args":{"answer":"..."},"id":"b"}])]
```
