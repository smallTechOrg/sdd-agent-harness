"""Structured observability events for Pandora.

Always-on observability: structlog renders JSON to stdout, one structured event
per question (and optional per-step debug events). Privacy boundary: these
helpers record only metadata/counts/cost — never raw dataset rows or values.

The structlog config is idempotent (configured once) and reads the level from
``AGENT_LOG_LEVEL`` via the settings singleton, falling back to ``INFO``.
"""

import logging
import os

import structlog

# Re-export of the project logger name used as the default.
DEFAULT_LOGGER_NAME = "pandora"

# Tracks the level we last configured with, so we only reconfigure when needed.
_configured_level: int | None = None


def _resolve_level(log_level: str | None) -> int:
    """Map a level name to its ``logging`` integer.

    Precedence: explicit arg → settings/env (``AGENT_LOG_LEVEL``) → ``INFO``.
    """
    name = log_level
    if name is None:
        name = os.environ.get("AGENT_LOG_LEVEL")
    if name is None:
        try:
            from config.settings import get_settings

            name = get_settings().log_level
        except Exception:
            name = None
    if name is None:
        name = "INFO"
    return getattr(logging, str(name).upper(), logging.INFO)


def configure_logging(log_level: str | None = None) -> None:
    """Configure structlog to emit JSON to stdout.

    Idempotent: a second call with the same effective level is a no-op so the
    config is not rebuilt (and bound-logger caches are not invalidated) on every
    import. Passing a new level reconfigures.
    """
    global _configured_level
    level = _resolve_level(log_level)
    if _configured_level == level and structlog.is_configured():
        return

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    _configured_level = level


def get_logger(name: str = DEFAULT_LOGGER_NAME) -> structlog.BoundLogger:
    """Return a configured structlog logger (JSON → stdout).

    Configures logging on first use so callers never get an unconfigured logger.
    """
    if _configured_level is None:
        configure_logging()
    # PrintLoggerFactory ignores the factory name, and the stdlib
    # ``add_logger_name`` processor needs a stdlib ``_record`` it never gets, so
    # bind the logger name explicitly to keep it in the JSON output.
    return structlog.get_logger().bind(logger=name)


def log_question_event(
    *,
    dataset_id: str,
    question_id: str,
    status: str,
    attempts: int = 0,
    exec_ms: int | float | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    **extra: object,
) -> None:
    """Emit one structured per-question event to stdout.

    Records metadata/counts/cost only — never raw dataset rows. ``status``
    selects the event name: anything other than ``"ok"`` is treated as a
    failure (``question_failed`` at error level); ``"ok"`` emits
    ``question_completed`` at info level.

    ``extra`` carries additional scalar metadata the runner wants on the event
    (e.g. ``node_sequence``, ``prompt_chars``, ``model``, ``error``). Callers
    must pass metadata only — this seam never receives the DataFrame.
    """
    log = get_logger(DEFAULT_LOGGER_NAME)
    fields = {
        "dataset_id": dataset_id,
        "question_id": question_id,
        "status": status,
        "attempts": attempts,
        "exec_ms": exec_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": cost_usd,
        **extra,
    }
    if status == "ok":
        log.info("question_completed", **fields)
    else:
        log.error("question_failed", **fields)


def log_step_event(
    *,
    question_id: str,
    step: str,
    index: int,
    elapsed_ms: int | float,
) -> None:
    """Emit an optional per-step debug event (one per node boundary).

    Mirrors the SSE step stream for observability. Debug level, so it is silent
    unless ``AGENT_LOG_LEVEL=DEBUG``.
    """
    get_logger(DEFAULT_LOGGER_NAME).debug(
        "step",
        question_id=question_id,
        step=step,
        index=index,
        elapsed_ms=elapsed_ms,
    )
