"""Conditional routing for the data-analyst graph.

Each step routes to ``handle_error`` if ``state["error"]`` is set, otherwise to
the next pipeline node.
"""
from graph.state import AgentState


def _route(nxt: str):
    """Return a routing function: -> handle_error on error, else -> nxt."""
    def router(state: AgentState) -> str:
        return "handle_error" if state.get("error") else nxt

    return router
