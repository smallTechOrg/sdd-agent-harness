from google import genai
from google.genai import types


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-pro"
    DEFAULT_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else self.DEFAULT_TIMEOUT_SECONDS
        )
        # google-genai expects the HTTP timeout in MILLISECONDS.
        timeout_ms = int(self._timeout_seconds * 1000)
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text
