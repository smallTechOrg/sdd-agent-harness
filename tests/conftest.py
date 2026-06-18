import pytest


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    import datachat.config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _reset_db_singletons():
    import datachat.db.session as s
    s._engine = None
    s._SessionLocal = None
    yield
    if s._engine:
        s._engine.dispose()
    s._engine = None
    s._SessionLocal = None
