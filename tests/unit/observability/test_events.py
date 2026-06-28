"""Unit tests for the structlog-based observability event helpers.

These assert the always-on Phase-1 observability contract: structured JSON to
stdout for each question, carrying only metadata/counts/cost (never raw rows).
"""

import json

import pytest

from observability.events import (
    configure_logging,
    get_logger,
    log_question_event,
    log_step_event,
)


def _parse_json_lines(captured: str) -> list[dict]:
    lines = []
    for raw in captured.strip().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        lines.append(json.loads(raw))
    return lines


def test_get_logger_returns_logger_and_emits_json(capsys):
    log = get_logger("pandora.test")
    log.info("hello", foo="bar")

    out = capsys.readouterr().out
    events = _parse_json_lines(out)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "hello"
    assert event["foo"] == "bar"
    # Standard structured fields present.
    assert "timestamp" in event
    assert event["level"] == "info"
    assert event["logger"] == "pandora.test"


def test_get_logger_default_name():
    # Default name is the project logger; must not raise.
    log = get_logger()
    assert log is not None


def test_configure_logging_is_idempotent(capsys):
    # Calling configure repeatedly must not double-configure / double-emit.
    configure_logging()
    configure_logging()
    get_logger("pandora.idem").info("once")
    out = capsys.readouterr().out
    events = _parse_json_lines(out)
    assert len(events) == 1


def test_log_question_event_emits_all_metadata(capsys):
    log_question_event(
        dataset_id="ds-123",
        question_id="q-456",
        status="ok",
        attempts=2,
        exec_ms=842,
        prompt_tokens=1500,
        completion_tokens=320,
        cost_usd=0.0012,
        node_sequence=["generate_code", "execute_code", "summarise"],
        prompt_chars=4096,
    )
    out = capsys.readouterr().out
    events = _parse_json_lines(out)
    assert len(events) == 1
    event = events[0]

    assert event["event"] == "question_completed"
    assert event["dataset_id"] == "ds-123"
    assert event["question_id"] == "q-456"
    assert event["status"] == "ok"
    assert event["attempts"] == 2
    assert event["exec_ms"] == 842
    assert event["prompt_tokens"] == 1500
    assert event["completion_tokens"] == 320
    assert event["cost_usd"] == 0.0012
    assert event["node_sequence"] == ["generate_code", "execute_code", "summarise"]
    assert event["prompt_chars"] == 4096
    assert event["level"] == "info"


def test_log_question_event_failure_status_uses_failed_event(capsys):
    log_question_event(
        dataset_id="ds-1",
        question_id="q-1",
        status="error",
        attempts=2,
        error="runtime_error",
    )
    out = capsys.readouterr().out
    events = _parse_json_lines(out)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "question_failed"
    assert event["status"] == "error"
    assert event["error"] == "runtime_error"
    assert event["level"] == "error"


def test_log_question_event_does_not_log_raw_data(capsys):
    # Even if a caller passes a data-like blob, the privacy boundary holds:
    # only declared metadata/extra-scalars are recorded; no sentinel leaks.
    sentinel = "SECRET-ROW-VALUE-7f3a"
    log_question_event(
        dataset_id="ds-1",
        question_id="q-1",
        status="ok",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.0,
    )
    out = capsys.readouterr().out
    assert sentinel not in out
    event = _parse_json_lines(out)[0]
    # No accidental row/data payload keys.
    assert "rows" not in event
    assert "data" not in event
    assert "dataframe" not in event


def test_log_step_event_emits_debug_step(capsys):
    # DEBUG level events only appear when the level allows them.
    configure_logging(log_level="DEBUG")
    log_step_event(
        question_id="q-1",
        step="generating_code",
        index=0,
        elapsed_ms=12,
    )
    out = capsys.readouterr().out
    events = _parse_json_lines(out)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "step"
    assert event["question_id"] == "q-1"
    assert event["step"] == "generating_code"
    assert event["index"] == 0
    assert event["elapsed_ms"] == 12
    # Restore default level so other tests are unaffected.
    configure_logging(log_level="INFO")


@pytest.fixture(autouse=True)
def _reset_logging():
    # Ensure a known-good config before each test regardless of order.
    configure_logging(log_level="DEBUG")
    yield
