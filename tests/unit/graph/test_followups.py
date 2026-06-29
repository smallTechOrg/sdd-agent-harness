"""Unit tests for parse_followups + the suggest_followups graph wiring."""
from graph.nodes import parse_followups
from graph.edges import after_answer


def test_parses_plain_lines():
    raw = "What is revenue by month?\nWhich region leads?\nTop products?"
    out = parse_followups(raw)
    assert out == [
        "What is revenue by month?",
        "Which region leads?",
        "Top products?",
    ]


def test_strips_numbering_and_bullets():
    raw = "1. First question?\n2) Second question?\n- Third question?"
    out = parse_followups(raw)
    assert out == ["First question?", "Second question?", "Third question?"]


def test_caps_at_three():
    raw = "\n".join(f"Q{i}?" for i in range(6))
    assert len(parse_followups(raw)) == 3


def test_drops_blank_lines_and_quotes():
    raw = '\n"What about averages?"\n\n  Trend over time?  \n'
    assert parse_followups(raw) == ["What about averages?", "Trend over time?"]


def test_empty_returns_empty_list():
    assert parse_followups("") == []
    assert parse_followups(None) == []


def test_after_answer_routes_to_suggest_followups_on_success():
    assert after_answer({"answer_text": "ok"}) == "suggest_followups"


def test_after_answer_routes_to_error():
    assert after_answer({"error": "boom"}) == "handle_error"
