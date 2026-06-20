# Usage-spec: langgraph

**Version: `langgraph` 1.2.x** (verify latest before pinning — a bump REFRESHES this file)
**Stamped: 2026-06 · LangGraph reached v1.0; this describes the 1.x line.**

Guards: `react-agent.md` (`agent/graph.py`, `agent/state.py`), `durability.md`, `guardrails-and-hitl.md`.
Our core hand-builds the ReAct loop as an explicit `StateGraph` — it does NOT use the prebuilt agent.

## The graph — explicit `StateGraph` (the shape the core relies on)
```python
from langgraph.graph import START, END, StateGraph

g = StateGraph(AgentState)
g.add_node("agent", agent_node)         # async def node(state) -> dict (partial state update)
g.add_node("tools", tools_node)
g.add_node("finalize", finalize_node)
g.add_edge(START, "agent")
g.add_conditional_edges("agent", route, {"tools": "tools", "finalize": "finalize"})
g.add_edge("tools", "agent")
g.add_edge("finalize", END)
app = g.compile()                       # compiled graph; await app.ainvoke(initial_state)
```
- ✅ `from langgraph.graph import START, END, StateGraph` — stable in 1.x.
- ✅ Nodes are `async def node(state) -> dict` returning a **partial** state update; the route fn returns the
  **name** of the next node (a key of the conditional-edges map).
- ✅ Drive with `await app.ainvoke(initial_state)` (async end-to-end).

## ⚠️ `AgentState.messages` is a PLAIN list — NO reducer
```python
from typing import TypedDict
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: list[BaseMessage]         # PLAIN list — the nodes return the full merged list themselves
    iterations: int
    answer: str | None
    run_id: str
```
- ❌ Do **NOT** annotate `messages: Annotated[list, add_messages]`. Our nodes already return
  `state["messages"] + [resp]` (the full list); an `add_messages` reducer would append on top of an
  already-complete list and **double-append**, corrupting the transcript and `/traces`. This is the single
  most likely silent breakage — do not "helpfully" add a reducer.

## Prebuilt agent — we DON'T use it (know why)
- ❌ Don't substitute `from langgraph.prebuilt import create_react_agent` for our hand-built loop. The core's
  `force_finalize` fallback chain, `max_iterations` sizing, and span emission live in the explicit nodes;
  the prebuilt agent hides them and breaks our gate's trajectory assertions. Generate the explicit graph.

## Checkpointer (only when durability/memory layer is ON)
```python
# local/demo:  from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver   # pip: langgraph-checkpoint-sqlite
# prod:        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver # pip: langgraph-checkpoint-postgres (asyncpg DSN)
app = g.compile(checkpointer=saver)
```
- ✅ Use the **async** savers (`...aio import Async*Saver`) — our stack is async; a sync saver blocks the loop.
- On resume the checkpointer returns a raw **dict** — read `cp["channel_values"]["messages"]`, NOT an
  attribute. Strip the stored `SystemMessage` and prepend a fresh one **each turn** (`C-MULTITURN-PROMPT`).
- ❌ Never a sync checkpointer / a sync DB driver here.

## HITL interrupt (only when guardrails+HITL layer is ON)
```python
from langgraph.types import interrupt, Command
# raise interrupt(payload) inside a node to pause; resume with app.ainvoke(Command(resume=value), config)
```
- These are in `langgraph.types` in 1.x — import from there, not a 0.x path.
