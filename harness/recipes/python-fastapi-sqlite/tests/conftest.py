import pytest


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Reset cached settings so env patches take effect in every test."""
    import agent.config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Isolated SQLite DB for each test — monkeypatches the session module."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from agent.db.models import Base
    import agent.db.session as session_module

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield engine
    engine.dispose()


@pytest.fixture
def _require_api_key():
    """Skip the test if the Anthropic API key is not set in .env."""
    from agent.config.settings import get_settings
    if not get_settings().anthropic_api_key:
        pytest.skip("AGENT_ANTHROPIC_API_KEY not set — required for integration tests")
