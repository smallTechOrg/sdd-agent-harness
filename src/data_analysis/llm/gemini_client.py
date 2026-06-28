import time
from google import genai
from google.genai import types
from data_analysis.config.settings import get_settings


class GeminiClient:
    def __init__(self):
        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("AGENT_GEMINI_API_KEY not set in .env")
        self._client = genai.Client(api_key=s.gemini_api_key)
        self._model = s.llm_model or "gemini-2.5-flash"

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema=None,
        max_retries: int = 3,
    ) -> tuple[str, int, int]:
        """
        Call Gemini. Returns (text, input_tokens, output_tokens).
        Retries up to max_retries on rate limit / server errors.
        """
        config_kwargs: dict = {}
        if system:
            config_kwargs["system_instruction"] = system
        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        cfg = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        for attempt in range(max_retries):
            try:
                resp = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=cfg,
                )
                text = resp.text or ""
                # Extract token counts from usage_metadata
                usage = getattr(resp, "usage_metadata", None)
                in_tok = getattr(usage, "prompt_token_count", 0) or 0
                out_tok = getattr(usage, "candidates_token_count", 0) or 0
                return text, in_tok, out_tok
            except Exception as e:
                err_str = str(e).lower()
                if attempt < max_retries - 1 and any(
                    x in err_str
                    for x in ["429", "quota", "503", "rate limit", "resource exhausted"]
                ):
                    time.sleep(2**attempt)
                    continue
                raise
        raise RuntimeError(f"Gemini call failed after {max_retries} retries")


_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
