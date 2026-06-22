from openai import OpenAI

from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult, estimate_cost_usd

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        """Create an OpenAI-compatible client pointed at OpenRouter for ``model``."""
        self._client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> LLMResult:
        """Send the prompt to OpenRouter and return the reply with usage and cost."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            timeout=60.0,
        )
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        return LLMResult(
            text=response.choices[0].message.content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost_usd(self._model, input_tokens, output_tokens),
        )
