"""Code-interpreter loop nodes (see spec/agent.md).

generate_code → execute_code → (summarize | retry generate_code | handle_error)

The LLM (via ``LLMClient``) only ever receives the bounded ``schema_summary`` and
the question — never the full dataframe, which is loaded locally inside
``execute_code`` from ``dataframe_path``.
"""

import re
from pathlib import Path

import pandas as pd

from execution.sandbox import SandboxError, run_code
from graph.state import AgentState
from llm.client import LLMClient
from observability.events import get_logger

log = get_logger("graph.nodes")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_ANALYZE_PROMPT_PATH = _PROMPTS_DIR / "analyze.md"

_CODE_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _load_analyze_prompt() -> str:
    return _ANALYZE_PROMPT_PATH.read_text(encoding="utf-8").strip()


def extract_code_block(text: str) -> str:
    """Pull the pandas code out of an LLM reply.

    Handles ```python / ```py fences and falls back to the raw text when the
    model returns bare code with no fence.
    """
    if not text:
        return ""
    matches = _CODE_FENCE_RE.findall(text)
    if matches:
        return matches[0].strip()
    return text.strip()


def _build_generate_prompt(state: AgentState) -> str:
    parts = [
        f"Dataset schema (the only view of the data you have):\n{state['schema_summary']}",
        f"\nQuestion: {state['question']}",
    ]
    prior_code = state.get("generated_code")
    prior_error = state.get("execution_error")
    if prior_code and prior_error:
        parts.append(
            "\nYour previous code raised an error. Fix it and try again.\n"
            f"Previous code:\n```python\n{prior_code}\n```\n"
            f"Error:\n{prior_error}"
        )
    return "\n".join(parts)


def generate_code(state: AgentState) -> AgentState:
    attempts = state.get("attempts", 0) + 1
    system = _load_analyze_prompt()
    prompt = _build_generate_prompt(state)

    reply = LLMClient().call_model(prompt, system=system)
    code = extract_code_block(reply)

    log.info(
        "graph.generate_code",
        run_id=state.get("run_id"),
        attempt=attempts,
        is_retry=bool(state.get("execution_error")),
        code_chars=len(code),
    )
    return {**state, "generated_code": code, "attempts": attempts}


def execute_code(state: AgentState) -> AgentState:
    code = state.get("generated_code") or ""
    # The full dataframe is loaded LOCALLY here — never placed in state, never sent to the LLM.
    df = pd.read_csv(state["dataframe_path"])

    try:
        result_repr, steps = run_code(code, df)
    except SandboxError as exc:
        log.info(
            "graph.execute_code",
            run_id=state.get("run_id"),
            attempt=state.get("attempts"),
            ok=False,
            error=str(exc),
        )
        return {**state, "execution_error": str(exc)}

    log.info(
        "graph.execute_code",
        run_id=state.get("run_id"),
        attempt=state.get("attempts"),
        ok=True,
        result_chars=len(result_repr),
    )
    return {
        **state,
        "execution_result": result_repr,
        "execution_steps": steps,
        "execution_error": None,
    }


def summarize(state: AgentState) -> AgentState:
    prompt = (
        "A data analyst ran code to answer a question about a dataset. "
        "Explain the answer to the user in plain language, in 1-3 sentences. "
        "State the computed value clearly. Do not show code.\n\n"
        f"Question: {state['question']}\n"
        f"Computed result:\n{state.get('execution_result', '')}\n"
        f"Intermediate steps:\n{state.get('execution_steps', '')}"
    )
    answer = LLMClient().call_model(prompt)

    log.info(
        "graph.summarize",
        run_id=state.get("run_id"),
        answer_chars=len(answer or ""),
    )
    return {**state, "answer": (answer or "").strip(), "status": "completed"}


def handle_error(state: AgentState) -> AgentState:
    error = state.get("execution_error") or "the analysis code could not be executed"
    attempts = state.get("attempts", 0)
    answer = (
        "Sorry — I could not compute an answer to that question after "
        f"{attempts} attempt(s). The generated analysis code kept failing. "
        "Try rephrasing the question or checking that the relevant columns exist."
    )

    log.info(
        "graph.handle_error",
        run_id=state.get("run_id"),
        attempts=attempts,
        error=error,
    )
    return {**state, "error": error, "answer": answer, "status": "failed"}
