# Pattern: context engineering (Layer 2)

What goes into the model's window each turn, assembled in one place. The window is a budget, not a bucket:
every token costs latency, money, and attention. **Generate this fresh at build time**, pinning the
*current* `langchain` / token-counter library (check the latest first — a guessed/old version 404s).

## The default: just-in-time, not stuffed
Pull context *progressively* — let the agent fetch what it needs via tools (`search_docs`, file reads, MCP
queries → `patterns/tools-and-mcp.md`) rather than pre-loading everything into the prompt. Stuffing the
window upfront degrades reasoning (lost-in-the-middle), inflates cost, and goes stale. Keep the *steady*
prompt small; let retrieval bring in the *specific* slice for the turn. → `patterns/retrieval.md`.

## One place to assemble the prompt
The system prompt lives in **`agent/runner.py`** as a single `SystemMessage`, built from `spec/product.md`
(domain instructions) — never scattered string-concat across nodes. The `agent_node` reads `state["messages"]`
as-is; assembly happens once, before the graph runs. Sections, in order:

1. **Role + goal** — who the agent is, the task it's solving (from `spec/product.md`).
2. **Operating rules** — tool-use policy, when to call `finish`, output contract (from capabilities).
3. **Available tools** — bound by the model, not restated in prose; only add usage hints it can't infer.
4. **Retrieved context** — *appended as a separate message at retrieval time*, never baked into the system prompt.

## Window management
A turn's window = system prompt + running `messages` + this turn's retrieved context. Two pressures to manage:

- **Budget** — count tokens before each `bound.ainvoke`. Reserve headroom for the response (`max_tokens`).
  When `used > limit * threshold` (e.g. 0.8), compact (below).
- **Relevance** — prune stale tool output. A 5KB search result that's been superseded is dead weight; replace
  old `ToolMessage` bodies with a one-line stub once their answer is captured in a later message.

## Compaction — summarize near the limit, PRESERVE the load-bearing facts
When the window nears its cap, replace the *middle* of the transcript with a summary, but **never drop**:
the **goal**, **decisions made**, **open items / unfinished sub-tasks**, and the **last few messages** verbatim.
Summarize the rest. This is lossy by design — protect what the agent still needs to act correctly.

## Code — `agent/context.py` (compaction helper)
```python
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

def count_tokens(model, messages: list[BaseMessage]) -> int:
    """Provider-accurate when available; cheap fallback otherwise."""
    try:
        return model.get_num_tokens_from_messages(messages)   # langchain chat models expose this
    except Exception:
        return sum(len(str(m.content)) for m in messages) // 4  # ~4 chars/token

async def compact(model, messages: list[BaseMessage], *, goal: str,
                  limit: int, threshold: float = 0.8, keep_last: int = 4) -> list[BaseMessage]:
    """If near the budget, summarize the middle; PRESERVE goal + decisions + open items + tail."""
    if count_tokens(model, messages) < limit * threshold:
        return messages
    system = messages[0] if messages and isinstance(messages[0], SystemMessage) else None
    body = messages[1:] if system else messages
    if len(body) <= keep_last:
        return messages
    head, tail = body[:-keep_last], body[-keep_last:]          # tail stays verbatim
    transcript = "\n".join(f"{m.type}: {m.content}" for m in head)
    instr = (f"GOAL: {goal}\nSummarize the conversation below. PRESERVE every decision made, "
             f"open/unfinished item, and fact needed to finish the goal. Drop chit-chat and "
             f"superseded tool output.\n\n{transcript}")
    summary = await model.ainvoke([HumanMessage(content=instr)])
    note = AIMessage(content=f"[summary of earlier turns]\n{summary.content}")
    return ([system] if system else []) + [note] + tail
```
Call it in `agent_node` right before `bound.ainvoke`: `state["messages"] = await compact(model,
state["messages"], goal=state["goal"], limit=settings.context_limit)`. The summarizing call should use the
same cheap runtime model (`agent/llm.py`); wrap it in a `span(..., "compact", "INTERNAL")` so compaction is
visible in `/traces` (→ `patterns/observability-and-evals.md`).

## Pruning vs. compaction
- **Prune** = drop/stub individual stale messages cheaply, no LLM call (e.g. truncate old `ToolMessage`
  bodies). Do this every turn — it's free.
- **Compact** = one LLM summarization pass when pruning isn't enough. Costs a call; do it only near the limit.

## Mandatory mechanics (do not omit)
- **Single assembly point** — the system prompt is built once in `runner.py`; nodes never restring it.
- **JIT default** — retrieval pulls context on demand; no upfront stuffing. → `patterns/retrieval.md`.
- **Compaction preserves** goal + decisions + open items + verbatim tail. Lossy elsewhere is fine.
- **Budget guard** — count tokens before each model call; reserve response headroom.
- **Long-term memory** (carrying context *across runs*) is a separate concern → `patterns/memory.md`.

## Gate (the test that proves it — run it, don't trust it)
With a `FakeModel` (no key → `patterns/react-agent.md`) and a tiny `limit`, feed a long message list and
assert `compact` (1) returns fewer tokens, (2) keeps the `SystemMessage` and the last `keep_last` messages
verbatim, and (3) still contains the goal string. → `workflows/gates.md`.
