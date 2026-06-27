"""GeminiProvider applies the spec-mandated timeout — no real key needed.

The Gemini SDK (google-genai) expects the HTTP timeout in MILLISECONDS via
``http_options``. These tests assert the seconds-valued setting is converted
correctly and plumbed onto the client, so a stalled call cannot hang forever.
"""
import pytest


def test_timeout_is_plumbed_in_milliseconds():
    from llm.providers.gemini import GeminiProvider

    provider = GeminiProvider(api_key="AIza-fake", model="gemini-2.5-flash", timeout_seconds=12.0)

    # SDK expects milliseconds.
    assert provider._client._api_client._http_options.timeout == 12000


def test_default_timeout_used_when_unset():
    from llm.providers.gemini import GeminiProvider

    provider = GeminiProvider(api_key="AIza-fake", model="gemini-2.5-flash")

    expected_ms = int(GeminiProvider.DEFAULT_TIMEOUT_SECONDS * 1000)
    assert provider._client._api_client._http_options.timeout == expected_ms


def test_client_passes_settings_timeout_to_gemini(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "AIza-fake")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("AGENT_LLM_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")

    import config.settings as m
    m._settings = None

    from llm.client import _make_provider
    provider = _make_provider()

    assert provider._client._api_client._http_options.timeout == 7000
