import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import data_analyst.config.settings as settings_module
import data_analyst.db.session as session_module
from data_analyst.db.models import Base


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    """A real SQLite-backed session — same driver as production."""
    db_url = f"sqlite:///{tmp_path}/test_metadata.db"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)

    with factory() as session:
        yield session
    engine.dispose()
