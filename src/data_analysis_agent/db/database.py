from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker, Session


class Database:
    """
    Encapsulates the master database connection for SQLite or PostgreSQL.

    Public interface: one method — execute(sql, params) → list[dict].

    Configure the backend via DATAANALYSIS_DATABASE_URL:
      SQLite    (default): sqlite:///data_analysis.db
      PostgreSQL:          postgresql+psycopg2://user:pass@host:5432/dbname
    """

    def __init__(self, url: str) -> None:
        """Create the engine and session factory for a SQLite or PostgreSQL URL."""
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.__engine: Engine = create_engine(url, echo=False, connect_args=connect_args)
        self.__session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.__engine, autoflush=False, autocommit=False
        )

    def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute a SQL statement and return all rows as a list of dicts.

        SELECT queries return one dict per row. DML (INSERT/UPDATE/DELETE)
        commits and returns an empty list.
        """
        with self.__engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            if result.returns_rows:
                return [dict(row._mapping) for row in result]
            conn.commit()
            return []

    # ------------------------------------------------------------------ #
    # Package-internal helpers — not part of the public API.              #
    # Used only by db/session.py to bridge to the SQLAlchemy ORM layer.  #
    # ------------------------------------------------------------------ #

    def _make_session(self) -> Session:
        """Return a new ORM session bound to this database's engine."""
        return self.__session_factory()

    def _init_schema(self) -> None:
        """Create all ORM-mapped tables on this engine if they do not exist."""
        from data_analysis_agent.db.models import Base
        Base.metadata.create_all(bind=self.__engine)

    def _dispose(self) -> None:
        """Dispose the engine and close its connection pool."""
        self.__engine.dispose()
