import pytest
import data_analysis_agent.config.settings as settings_module
import data_analysis_agent.tools.mcp.pool as pool_module


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Reset cached settings so env patches take effect in every test."""
    settings_module._settings = None
    yield
    settings_module._settings = None


@pytest.fixture(autouse=True)
def _reset_pool_manager():
    """Tear down the session-pool manager after each test so pools/locks don't leak."""
    yield
    if pool_module._manager is not None:
        pool_module._manager.close_all()
        pool_module._manager = None
