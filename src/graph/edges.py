"""Conditional routing functions for the plan-execute graph.

Implements the conditional-edge table in ``spec/agent.md`` -> "Graph / Flow
Topology". The plan/generate_code/synthesize error gates are simple
``error``-presence checks (inlined in agent.py); the non-trivial one — the
self-correction loop after execution — lives here as ``route_after_execute``.
"""

from __future__ import annotations

from graph.state import AgentState

# Default matches spec/.env.example (AGENT_MAX_RETRIES=1): exactly one
# self-correction retry. Read from settings defensively.
_DEFAULT_MAX_RETRIES = 1


def _max_retries() -> int:
    try:
        from config.settings import get_settings

        value = getattr(get_settings(), "max_retries", None)
        return _DEFAULT_MAX_RETRIES if value is None else int(value)
    except Exception:
        return _DEFAULT_MAX_RETRIES


def route_after_error(state: AgentState) -> str:
    """Generic error gate used after plan / generate_code / synthesize."""
    return "handle_error" if state.get("error") else "__continue__"


def route_after_execute(state: AgentState) -> str:
    """Route out of ``execute_local`` (the self-correction loop).

    - exec_error AND retry_count < AGENT_MAX_RETRIES -> ``generate_code`` (retry once)
    - exec_error AND retry_count >= AGENT_MAX_RETRIES -> ``handle_error``
    - no exec_error                                   -> ``synthesize``

    The retry_count is incremented as part of choosing the retry branch so the
    graph cannot loop forever (the state update is returned by the caller in
    agent.py via the increment wrapper).
    """
    if state.get("exec_error"):
        if state.get("retry_count", 0) < _max_retries():
            return "generate_code"
        return "handle_error"
    return "synthesize"
