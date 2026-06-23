"""Graph-compile contract: the data-analyst graph compiles with NO env vars."""


def test_graph_compiles():
    """Graph compiles without requiring any env vars (key, db, duckdb)."""
    from graph.agent import agentic_ai

    assert agentic_ai is not None


def test_graph_has_data_analyst_nodes():
    """The compiled graph exposes the spec pipeline + error nodes."""
    from graph.agent import agentic_ai

    nodes = set(agentic_ai.get_graph().nodes.keys())
    for name in (
        "profile_schema",
        "generate_sql",
        "execute_sql",
        "narrate",
        "finalize",
        "handle_error",
    ):
        assert name in nodes, f"missing node: {name}"
