from config.settings import get_settings


def _resolve_provider_name() -> str:
    s = get_settings()
    provider = s.llm_provider
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
    return provider


def _make_provider(name: str):
    s = get_settings()
    if name == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model)
    if name == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=s.gemini_api_key, model=s.llm_model)
    raise RuntimeError(f"Unknown LLM provider: {name!r}. Supported: anthropic, gemini")


class LLMClient:
    def __init__(self) -> None:
        self.provider_name = _resolve_provider_name()
        self._provider = _make_provider(self.provider_name)

    def call_model(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
    ):
        """Call the configured provider. `model` overrides the default for this
        one call; `tools` enables tool-calling; `messages` passes a full ReAct
        history (mutually exclusive with `prompt`)."""
        return self._provider.call_model(
            prompt, system=system, model=model, tools=tools, messages=messages
        )

    def assistant_turn(self, resp):
        return self._provider.assistant_turn(resp)

    def tool_results_turn(self, results, names=None):
        # Gemini keys by name; Anthropic ignores the extra arg.
        try:
            return self._provider.tool_results_turn(results, names=names)
        except TypeError:
            return self._provider.tool_results_turn(results)
