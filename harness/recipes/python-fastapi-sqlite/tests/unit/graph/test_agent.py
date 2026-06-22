def test_graph_compiles():
    """Graph compiles without requiring any env vars."""
    from agent.graph.agent import agentic_ai
    assert agentic_ai is not None
