from data_analysis_agent.llm.providers.base import LLMProvider


def create_llm_provider() -> LLMProvider:
    """Build the LLM provider chosen by settings: OpenRouter when keyed, else stub."""
    from data_analysis_agent.config.settings import get_settings
    settings = get_settings()

    if settings.resolved_llm_provider == "openrouter":
        from data_analysis_agent.llm.providers.openrouter import OpenRouterLLMProvider
        return OpenRouterLLMProvider(
            api_key=settings.openrouter_api_key.split("#")[0].strip(),
            model=settings.llm_model,
        )

    from data_analysis_agent.llm.providers.stub import StubLLMProvider
    return StubLLMProvider()
