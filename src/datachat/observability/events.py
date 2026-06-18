"""Structured logging (structlog) + token/cost accounting — baseline observability.

Every log line is JSON bound to run_id (and session/dataset where relevant). OTel GenAI
spans wrap each Gemini call and tool call. Never log dataset rows, raw CSV, or the API key.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import structlog
from opentelemetry import trace

from datachat.config.settings import get_settings

_configured = False
_tracer = trace.get_tracer("datachat")

# Gemini 2.5 Flash approximate USD per 1M tokens (input / output). Configurable upstream.
_COST_PER_1M_INPUT = 0.30
_COST_PER_1M_OUTPUT = 2.50


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
    _configured = True


def get_logger(**bind):
    configure_logging()
    return structlog.get_logger().bind(**bind)


@contextmanager
def span(name: str, **attrs):
    """Context manager for an OTel GenAI span around a model/tool call."""
    with _tracer.start_as_current_span(name) as span_obj:
        for k, v in attrs.items():
            span_obj.set_attribute(k, v)
        yield span_obj


def estimate_cost_usd(tokens_input: int, tokens_output: int) -> float:
    return round(
        tokens_input / 1_000_000 * _COST_PER_1M_INPUT
        + tokens_output / 1_000_000 * _COST_PER_1M_OUTPUT,
        6,
    )
