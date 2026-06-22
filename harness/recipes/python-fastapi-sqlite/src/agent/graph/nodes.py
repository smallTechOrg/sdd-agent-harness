from pathlib import Path

from agent.graph.state import AgentState
from agent.llm.client import LLMClient

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "transform.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def transform_text(state: AgentState) -> AgentState:
    try:
        prompt_template = _load_prompt()
        result = LLMClient().call_model(
            f"{prompt_template}\n\nInput: {state['input_text']}"
        )
        return {**state, "output_text": result}
    except Exception as exc:
        return {**state, "error": str(exc)}


def handle_error(state: AgentState) -> AgentState:
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}
