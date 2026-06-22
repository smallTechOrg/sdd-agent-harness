from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult


class LLMClient:
    """Thin wrapper delegating completion calls to a configured provider."""

    def __init__(self, provider: LLMProvider) -> None:
        """Store the provider this client delegates completions to."""
        self._provider = provider

    def complete(self, prompt: str) -> LLMResult:
        """Complete a prompt via the wrapped provider and return its result."""
        return self._provider.complete(prompt)


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the process-wide :class:`LLMClient` singleton, built from settings."""
    global _client
    if _client is None:
        from data_analysis_agent.llm.providers.factory import create_llm_provider
        _client = LLMClient(create_llm_provider())
    return _client
