from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    input_text: str
    output_text: str
    error: str | None
