"""Settings + provider auto-detection — no LLM key required."""
import pytest
import os


def test_auto_detects_anthropic(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")

    import config.settings as m
    m._settings = None
    s = m.get_settings()
    assert s.anthropic_api_key == "sk-ant-fake"
    assert s.gemini_api_key == ""


def test_auto_detects_gemini(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "AIza-fake")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")

    import config.settings as m
    m._settings = None
    s = m.get_settings()
    assert s.gemini_api_key == "AIza-fake"


def test_provider_raises_with_no_key(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")

    import config.settings as m
    m._settings = None

    from llm.client import _resolve_provider_name
    with pytest.raises(RuntimeError, match="No LLM provider configured"):
        _resolve_provider_name()


def test_explicit_provider_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "AIza-fake")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")

    import config.settings as m
    m._settings = None
    s = m.get_settings()
    assert s.llm_provider == "gemini"
