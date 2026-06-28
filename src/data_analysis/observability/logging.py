import logging
import structlog
from typing import Any


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for JSON output to stdout.
    Called once at application startup.
    """
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str = "data_analysis") -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)


def log_query_completed(
    query_run_id: str,
    question: str,
    status: str,
    iterations_used: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    elapsed_s: float,
) -> None:
    """
    Emit a structured per-query audit log entry to stdout.
    Called at the end of each SSE query run.
    """
    logger = get_logger("query")
    logger.info(
        "query_completed",
        query_run_id=query_run_id,
        question=question[:200],  # truncate to 200 chars
        status=status,
        iterations_used=iterations_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        elapsed_s=round(elapsed_s, 3),
    )
