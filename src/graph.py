"""The ReAct Deep-Agent loop (harness/patterns/react-agent.md).

agent → (tools → agent)* → finalize. The model is bound to the tools; tool calls run and the loop
continues; on `finish` (or the iteration cap) it finalizes. build_graph takes an optional checkpointer so
Phase 3 (multi-turn) can compile with one — one new kwarg, nothing else changes.
"""
from langchain_core.messages import ToolMessage, AIMessage as _AIMessage
from langgraph.graph import END, START, StateGraph

from .config import get_settings
from .observability import span
from .state import AgentState
from .tools import FINISH, TOOL_MAP, TOOLS


def content_to_text(content) -> str:
    """Flatten a message's content to plain text.

    Some providers (e.g. Gemini via langchain-google-genai) return `content` as a list of content blocks
    — a text block plus a base64 'thought-signature' block. Keep the text, drop the rest, so the persisted
    answer is a clean string (and bindable to the Text column).
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict) and b.get("type") in (None, "text") and b.get("text"):
                parts.append(b["text"])
        return "\n".join(p for p in parts if p) or ""
    return str(content)


def build_graph(model, checkpointer=None):
    bound = model.bind_tools(TOOLS)
    settings = get_settings()

    async def agent_node(state):
        async with span(state["run_id"], f"chat {settings.llm_model}", "LLM") as sp:
            resp = await bound.ainvoke(state["messages"])
            if (u := getattr(resp, "usage_metadata", None)):
                sp["tokens"] = u
        return {"messages": state["messages"] + [resp], "iterations": state["iterations"] + 1}

    async def tools_node(state):
        out = []
        for tc in state["messages"][-1].tool_calls:
            if tc["name"] == FINISH:
                continue
            tool = TOOL_MAP.get(tc["name"])
            async with span(state["run_id"], f"execute_tool.{tc['name']}", "TOOL", args=tc["args"]) as sp:
                result = tool.invoke(tc["args"]) if tool else f"unknown tool: {tc['name']}"
                sp["result_preview"] = str(result)[:300]
            out.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": state["messages"] + out}

    async def finalize_node(state):
        last = state["messages"][-1]
        answer = None
        chart_spec = None

        # Happy path: last message has an explicit finish tool call
        for tc in getattr(last, "tool_calls", None) or []:
            if tc["name"] == FINISH:
                answer = tc["args"].get("answer")
                chart_spec = tc["args"].get("chart_spec") or None

        # Force-finalize path (iteration cap hit): scan backwards for any finish call
        if answer is None:
            for msg in reversed(state["messages"][:-1]):
                for tc in getattr(msg, "tool_calls", None) or []:
                    if tc["name"] == FINISH and tc["args"].get("answer"):
                        answer = tc["args"]["answer"]
                        chart_spec = tc["args"].get("chart_spec") or None
                        break
                if answer is not None:
                    break

        # Fall back to last AIMessage text content (may be empty on Gemini when tool_calls present)
        if answer is None:
            answer = getattr(last, "content", None)

        # Last resort: summarise the last tool result so the user gets partial information
        if not content_to_text(answer):
            last_tool = next(
                (m for m in reversed(state["messages"]) if isinstance(m, ToolMessage) and m.content),
                None,
            )
            if last_tool:
                answer = (
                    "I gathered the following data but ran out of steps to complete the analysis:\n\n"
                    + last_tool.content
                )

        return {
            "answer": content_to_text(answer) or "(analysis incomplete — no data retrieved)",
            "chart_spec": chart_spec,
        }

    def route(state):
        if state["iterations"] >= settings.max_iterations:
            return "finalize"                              # force_finalize on runaway
        tcs = getattr(state["messages"][-1], "tool_calls", None)
        if tcs:
            return "finalize" if any(t["name"] == FINISH for t in tcs) else "tools"
        return "finalize"

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", "finalize": "finalize"})
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
