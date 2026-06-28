"""Conditional-edge routing for the Pandora analysis graph (see spec/agent.md).

The only loop in Phase 1 is a single bounded retry-on-error: on a static
reject or a runtime/timeout/memory error, the error is fed back to
``generate_code`` once, then we re-run. ``attempts`` increments per
regeneration, so the loop cannot run forever.
"""

from graph.state import AgentState

MAX_ATTEMPTS = 1


def after_validate(state: AgentState) -> str:
    if state.get("last_error"):
        return "generate_code" if state.get("attempts", 0) < MAX_ATTEMPTS else "handle_error"
    return "execute_code"


def after_execute(state: AgentState) -> str:
    if state.get("last_error"):
        return "generate_code" if state.get("attempts", 0) < MAX_ATTEMPTS else "handle_error"
    return "summarise"


def after_summarise(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "finalize"
