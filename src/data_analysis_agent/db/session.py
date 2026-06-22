from contextlib import contextmanager
from collections.abc import Generator

from sqlalchemy.orm import Session

from data_analysis_agent.db.database import Database

_db: Database | None = None


def _get_database() -> Database:
    """Return the process-wide :class:`Database` singleton, creating it on first use."""
    global _db
    if _db is None:
        from data_analysis_agent.config.settings import get_settings
        _db = Database(get_settings().database_url)
    return _db


def get_db() -> Database:
    """Return the singleton Database instance for raw SQL access."""
    return _get_database()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a SQLAlchemy ORM session."""
    with _get_database()._make_session() as sess:
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise


@contextmanager
def create_db_session() -> Generator[Session, None, None]:
    """Standalone context manager for graph nodes and scripts."""
    with _get_database()._make_session() as sess:
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise


def init_db() -> None:
    """Create all ORM-mapped tables if they do not exist."""
    _get_database()._init_schema()
