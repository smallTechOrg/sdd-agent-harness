import pytest


@pytest.fixture(autouse=True)
def _reset_data_analysis_settings():
    """Reset data_analysis settings singleton before each test."""
    try:
        import data_analysis.config.settings as m
        m._settings = None
        yield
        m._settings = None
    except ImportError:
        yield
