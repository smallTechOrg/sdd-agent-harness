import os

import google.generativeai as genai

from analyst.errors import AnalystError


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self._api_key = api_key
        self._model = model
        genai.configure(api_key=api_key)

    def generate_sql(self, prompt: str) -> str:
        """Call Gemini and return the generated SQL string."""
        try:
            model = genai.GenerativeModel(self._model)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise AnalystError("llm_unavailable", f"Gemini API error: {e}", 502)
