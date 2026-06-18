from datachat.config.settings import get_settings


def test_defaults(monkeypatch):
    monkeypatch.setenv("DATACHAT_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("DATACHAT_GEMINI_API_KEY", "")
    s = get_settings()
    assert s.database_url == "sqlite:///./test.db"
    assert s.llm_model == "gemini-2.5-flash"
    assert s.max_iterations == 10
    assert s.resolved_llm_provider == "stub"


def test_resolved_provider_gemini(monkeypatch):
    monkeypatch.setenv("DATACHAT_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("DATACHAT_GEMINI_API_KEY", "my-key")
    s = get_settings()
    assert s.resolved_llm_provider == "gemini"


def test_resolved_provider_strips_inline_comment(monkeypatch):
    monkeypatch.setenv("DATACHAT_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("DATACHAT_GEMINI_API_KEY", "  # just a comment")
    s = get_settings()
    assert s.resolved_llm_provider == "stub"
