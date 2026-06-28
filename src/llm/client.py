from config.settings import get_settings
from llm.usage import LLMResult, Usage, usage_from_dict


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

    def call_model(self, prompt: str, *, system: str | None = None) -> LLMResult:
        """Call the provider and return an ``LLMResult`` (``.text`` + ``.usage``).

        ``str(result)`` yields the answer text, so callers that treat the return
        as text continue to work; ``result.usage`` carries token counts and cost.
        """
        raw = self._provider.call_model(prompt, system=system)

        # Providers may return either (text, usage_dict) or a plain str.
        if isinstance(raw, tuple):
            text, usage_dict = raw
        else:
            text, usage_dict = raw, None

        model = getattr(self._provider, "_model", "") or ""
        if usage_dict is None:
            usage = Usage(
                prompt_tokens=0, completion_tokens=0, cost_usd=0.0, model=model
            )
        else:
            usage = usage_from_dict(usage_dict, model)

        return LLMResult(text=text or "", usage=usage)
