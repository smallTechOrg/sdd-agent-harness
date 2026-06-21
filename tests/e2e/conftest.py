"""e2e overrides — the browser journey drives the LIVE server (its own DB on disk), so the unit-suite's
autouse create/drop fixture must not run here."""
import pytest


@pytest.fixture(autouse=True)
def _fresh_db():
    yield
