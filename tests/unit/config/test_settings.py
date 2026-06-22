from data_analyst.config.settings import Settings


def test_defaults():
    s = Settings()
    assert s.llm_model == "gemini-2.5-flash"
    assert s.llm_model_escalation == "gemini-2.5-pro"
    assert s.port == 8001
    assert s.sample_rows == 5


def test_auto_resolves_to_stub_without_key():
    s = Settings(llm_provider="auto", gemini_api_key="")
    assert s.resolved_llm_provider == "stub"


def test_auto_resolves_to_gemini_with_key():
    s = Settings(llm_provider="auto", gemini_api_key="real-key")
    assert s.resolved_llm_provider == "gemini"


def test_inline_comment_stripped_from_provider():
    s = Settings(llm_provider="stub   # auto | gemini | stub", gemini_api_key="k")
    assert s.resolved_llm_provider == "stub"


def test_inline_comment_stripped_from_key():
    s = Settings(llm_provider="auto", gemini_api_key="   # no key here")
    assert s.resolved_llm_provider == "stub"
