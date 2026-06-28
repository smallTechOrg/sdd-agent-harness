from google import genai
from google.genai import types


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> tuple[str, dict]:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        usage = self._usage_dict(response)
        return response.text, usage

    def _usage_dict(self, response) -> dict:
        metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(metadata, "prompt_token_count", None) or 0
        completion_tokens = getattr(metadata, "candidates_token_count", None) or 0
        return {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "model": self._model,
        }
