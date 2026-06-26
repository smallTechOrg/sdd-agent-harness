import uuid

from google import genai
from google.genai import types

from llm.base import BaseProvider, price
from llm.response import LLMResponse, ToolCall


class GeminiProvider(BaseProvider):
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        used_model = model or self._model
        cfg: dict = {}
        if system:
            cfg["system_instruction"] = system
        if tools:
            cfg["tools"] = [types.Tool(**t) for t in tools]
        config = types.GenerateContentConfig(**cfg) if cfg else None

        response = self._client.models.generate_content(
            model=used_model,
            contents=messages if messages is not None else prompt,
            config=config,
        )

        text = response.text or ""
        tool_calls: list[ToolCall] = []
        for part in _parts(response):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                # Gemini has no call id — synthesise one to tie result→call.
                tool_calls.append(
                    ToolCall(id=str(uuid.uuid4()), name=fc.name, args=dict(fc.args or {}))
                )

        usage = response.usage_metadata
        tokens_in = usage.prompt_token_count or 0
        tokens_out = usage.candidates_token_count or 0
        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=used_model,
            cost_usd=price(used_model, tokens_in, tokens_out),
            tool_calls=tool_calls,
        )

    # --- ReAct message-shaping (Gemini keys tool results by name, not id) ---

    @staticmethod
    def assistant_turn(resp: LLMResponse) -> dict:
        parts: list[dict] = [{"text": resp.text}] if resp.text else []
        parts += [{"function_call": {"name": tc.name, "args": tc.args}} for tc in resp.tool_calls]
        return {"role": "model", "parts": parts}

    @staticmethod
    def tool_results_turn(results, names=None) -> dict:
        names = names or [c for c, _ in results]
        return {"role": "user", "parts": [
            {"function_response": {"name": n, "response": {"result": t}}}
            for (_, t), n in zip(results, names)]}


def _parts(response):
    try:
        return response.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return []
