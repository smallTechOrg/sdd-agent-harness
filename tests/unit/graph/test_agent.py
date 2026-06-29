"""Graph wiring + edge + parsing unit tests — no LLM key required."""
from graph.edges import after_generate_sql, after_execute, after_answer, MAX_SQL_RETRIES
from graph.nodes import parse_sql


def test_graph_compiles():
    from graph.agent import agentic_ai
    assert agentic_ai is not None


def test_after_generate_sql_routes_to_execute_when_ok():
    assert after_generate_sql({"sql": "SELECT 1"}) == "execute_sql"


def test_after_generate_sql_routes_to_error():
    assert after_generate_sql({"error": "boom"}) == "handle_error"


def test_after_execute_success_goes_to_answer():
    assert after_execute({"result_rows": [{"x": 1}]}) == "answer"


def test_after_execute_retries_when_error_and_under_max():
    state = {"sql_error": "Binder Error", "sql_attempts": 1}
    assert after_execute(state) == "generate_sql"


def test_after_execute_handles_error_when_exhausted():
    state = {"sql_error": "Binder Error", "sql_attempts": MAX_SQL_RETRIES}
    assert after_execute(state) == "handle_error"


def test_after_answer_routes():
    # On success the answer node routes into the Phase-2 enrichment node.
    assert after_answer({"answer_text": "hi"}) == "suggest_followups"
    assert after_answer({"error": "boom"}) == "handle_error"


def test_parse_sql_strips_fences():
    raw = "Here you go:\n```sql\nSELECT sum(revenue) AS total FROM data;\n```\n"
    assert parse_sql(raw) == "SELECT sum(revenue) AS total FROM data;"


def test_parse_sql_strips_bare_fences():
    raw = "```\nSELECT 1;\n```"
    assert parse_sql(raw) == "SELECT 1;"


def test_parse_sql_plain_passthrough():
    assert parse_sql("SELECT 1;") == "SELECT 1;"


def test_parse_sql_handles_none():
    assert parse_sql(None) == ""
