from collections.abc import Iterator

from config.settings import get_settings
from llm.providers.gemini import StreamChunk, Usage

__all__ = ["LLMClient", "Usage", "StreamChunk"]


def _make_provider():
    s = get_settings()
    provider = s.llm_provider

    # auto-detect from whichever key is set
    if not provider:
        if s.anthropic_api_key:
            provider = "anthropic"
        elif s.gemini_api_key:
            provider = "gemini"
        else:
            raise RuntimeError(
                "No LLM provider configured. Set AGENT_ANTHROPIC_API_KEY or "
                "AGENT_GEMINI_API_KEY in .env, or set AGENT_LLM_PROVIDER explicitly."
            )

    if provider == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model)
    if provider == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=s.gemini_api_key, model=s.llm_model)

    raise RuntimeError(f"Unknown LLM provider: {provider!r}. Supported: anthropic, gemini")


class LLMClient:
    def __init__(self) -> None:
        self._provider = _make_provider()

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self._provider.call_model(prompt, system=system)

    def call_model_with_usage(
        self, prompt: str, *, system: str | None = None
    ) -> tuple[str, Usage]:
        """Generate once, returning (text, Usage).

        Usage(prompt_tokens, completion_tokens) is captured from the provider's
        response usage metadata. Providers that do not implement usage capture
        fall back to text-only with zeroed Usage.
        """
        provider = self._provider
        if hasattr(provider, "call_model_with_usage"):
            return provider.call_model_with_usage(prompt, system=system)
        return provider.call_model(prompt, system=system), Usage()

    def stream_model(
        self, prompt: str, *, system: str | None = None
    ) -> Iterator[StreamChunk]:
        """Stream generation, yielding StreamChunk(text, usage).

        Each yielded StreamChunk carries an incremental `text` delta. `usage` is
        populated on chunks that expose token counts; the LAST chunk with a
        non-None `usage` holds the final cumulative prompt/completion tokens.
        Callers accumulate text and retain the most recent non-None usage.

        Providers without native streaming degrade to a single chunk carrying
        the full text plus the call's usage.
        """
        provider = self._provider
        if hasattr(provider, "stream_model"):
            yield from provider.stream_model(prompt, system=system)
            return
        text, usage = self.call_model_with_usage(prompt, system=system)
        yield StreamChunk(text=text, usage=usage)
