from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from analyst.config.settings import get_settings
from analyst.db.models import Base


def _build_sync_url(url: str) -> str:
    """Ensure the URL uses the synchronous SQLite driver by stripping +aiosqlite."""
    return url.replace("sqlite+aiosqlite:///", "sqlite:///").replace(
        "sqlite+aiosqlite:/", "sqlite://"
    )


def _make_engine():
    settings = get_settings()
    sync_url = _build_sync_url(settings.database_url)
    return create_engine(sync_url, connect_args={"check_same_thread": False})


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables if they do not exist. Used for dev; Alembic owns prod."""
    Base.metadata.create_all(bind=engine)
