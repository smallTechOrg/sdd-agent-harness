"""AgentState — the working memory of one run (harness/patterns/react-agent.md).

WARNING: `messages` is a PLAIN list — NO Annotated[list, add_messages] reducer. The graph nodes return the
full updated list themselves (state["messages"] + [resp]); an add_messages reducer would double-append and
corrupt the transcript and /traces history.
"""
from typing import TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: list[BaseMessage]
    iterations: int
    answer: str | None
    chart_spec: str | None
    run_id: str
