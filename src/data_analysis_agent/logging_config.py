import logging
import logging.handlers
from pathlib import Path

import structlog

_MAX_LOG_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5


def configure_logging(log_level: str = "INFO", log_file: str = "logs/app.log") -> None:
    """Configure structlog JSON logging plus a rotating file handler.

    Args:
        log_level: Root log level name, e.g. ``"INFO"`` or ``"DEBUG"``.
        log_file: Path to the rotating log file; parent dirs are created.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _configure_structlog()
    root = logging.getLogger()
    root.setLevel(level)
    _attach_file_handler(root, log_path, level)


def _configure_structlog() -> None:
    """Install the structlog processor chain that renders JSON log lines."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _attach_file_handler(root: logging.Logger, log_path: Path, level: int) -> None:
    """Add a rotating file handler once, avoiding duplicates on repeated calls."""
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
