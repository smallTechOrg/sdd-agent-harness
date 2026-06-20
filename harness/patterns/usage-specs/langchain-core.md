# Usage-spec: langchain / langchain-core (+ provider package)

**Version: `langchain` 1.x · `langchain-core` 1.x** (verify latest before pinning — a bump REFRESHES this file)
**Stamped: 2026-06 · LangChain reached v1.0; this describes the 1.x line, not the 0.x examples in training data.**

Guards: `model-and-providers.md` (`agent/llm.py`), `tools-and-mcp.md` (`agent/tools.py`),
`context-engineering.md`. The core relies on exactly these shapes.

## The accessor — `init_chat_model` (the ONE way the core gets a model)
```python
from langchain.chat_models import init_chat_model        # CORRECT in 1.x
model = init_chat_model(model, model_provider=provider, api_key=key)
```
- ✅ `from langchain.chat_models import init_chat_model` — the v1 home.
- ❌ Do NOT `from langchain_core.language_models import init_chat_model` — wrong package.
- ❌ Do NOT instantiate a provider client directly (`ChatAnthropic(...)`, `ChatOpenAI(...)`) inside nodes —
  the whole point is provider-as-config (`C-LLM-ACCESSOR`). Only `agent/llm.py` calls `init_chat_model`.
- `model_provider` dispatches to the installed provider pkg (`langchain-anthropic` / `langchain-openai` /
  `langchain-google-genai`) — that package MUST be installed or `init_chat_model` raises at call time.

## Messages — the only message types the core uses
```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage
```
- ✅ Import message classes from `langchain_core.messages` (stable across 1.x).
- `AIMessage.content` may be a **list of parts** (reasoning / multimodal), not a `str`. **Always coerce
  before string ops** — `str(content)` on a list yields `"[{'type':...}]"`, not text:
  ```python
  raw = msg.content
  if isinstance(raw, list):
      raw = "\n".join(p["text"] for p in raw if isinstance(p, dict) and p.get("type") == "text")
  content = raw or ""
  ```
- Tool calls live on `msg.tool_calls` — a list of `{"name","args","id"}` dicts. Use `getattr(m,"tool_calls",None) or []`
  (not every message has the attribute).

## Tools — `@tool` from `langchain_core.tools`
```python
from langchain_core.tools import tool

@tool
def search_docs(query: str) -> str:
    """One-line docstring — the model reads this as the tool description."""
    return "..."                 # return a STRING (or JSON string); FAIL SOFT, never raise
```
- ✅ Typed signature → LangChain derives the JSON schema from the annotations. Keep args JSON-serializable.
- ✅ A non-empty one-line docstring is REQUIRED — it is the description the model sees.
- ❌ Don't raise from a tool body — return `"error: ..."` so the loop can recover (`C-DEGRADE`); an unhandled
  raise kills the run.
- Bind with `model.bind_tools(TOOLS)`; dispatch with `tool.invoke(tc["args"])`.

## usage_metadata — type-guard before reading tokens
`resp.usage_metadata` is a **TypedDict on some providers (a plain `dict`)** and an object on others.
`getattr(u,"input_tokens",0)` silently returns 0 on a dict. Use:
```python
u = getattr(resp, "usage_metadata", None)
inp = u.get("input_tokens", 0) if isinstance(u, dict) else getattr(u, "input_tokens", 0)
```

## Structured output — don't combine with tools
```python
structured = get_model().with_structured_output(MyPydanticModel)
result = await structured.ainvoke(messages)   # validated instance, not a string
```
- ❌ Don't call `.with_structured_output(...)` and `.bind_tools(...)` on the **same** call — pick one per
  invocation (structured extraction OR the tool-calling ReAct loop).

## v1 gotchas (the things training-data 0.x examples get wrong)
- The legacy `langchain.agents.initialize_agent` / `AgentExecutor` 0.x constructors are gone/deprecated — we
  don't use them anyway (we build the loop with LangGraph — `langgraph.md`). Don't reach for them.
- Always `await` the async path (`ainvoke`); the core is async end-to-end.
