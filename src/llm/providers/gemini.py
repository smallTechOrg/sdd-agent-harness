from google import genai
from google.genai import types

from llm.response import LLMResponse

# $/million tokens — Gemini 2.5 Flash
_INPUT_COST_PER_M = 0.15
_OUTPUT_COST_PER_M = 0.60


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        usage = response.usage_metadata
        tokens_in = usage.prompt_token_count or 0
        tokens_out = usage.candidates_token_count or 0
        cost = (tokens_in * _INPUT_COST_PER_M + tokens_out * _OUTPUT_COST_PER_M) / 1_000_000
        return LLMResponse(
            text=response.text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=self._model,
            cost_usd=cost,
        )
