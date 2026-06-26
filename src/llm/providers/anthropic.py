import anthropic as _sdk

from llm.response import LLMResponse

# $/million tokens — Sonnet 4.6
_INPUT_COST_PER_M = 3.0
_OUTPUT_COST_PER_M = 15.0


class AnthropicProvider:
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = _sdk.Anthropic(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        msg = self._client.messages.create(**kwargs)
        tokens_in = msg.usage.input_tokens
        tokens_out = msg.usage.output_tokens
        cost = (tokens_in * _INPUT_COST_PER_M + tokens_out * _OUTPUT_COST_PER_M) / 1_000_000
        return LLMResponse(
            text=msg.content[0].text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=msg.model,
            cost_usd=cost,
        )
