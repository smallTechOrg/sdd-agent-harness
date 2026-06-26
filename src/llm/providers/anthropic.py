import anthropic as _sdk

from llm.base import BaseProvider, price
from llm.response import LLMResponse, ToolCall


class AnthropicProvider(BaseProvider):
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = _sdk.Anthropic(api_key=api_key)
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
        kwargs: dict = dict(
            model=model or self._model,
            max_tokens=4096,
            # ReAct passes a full message history; one-shot calls pass a prompt.
            messages=messages or [{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        msg = self._client.messages.create(**kwargs)

        text = "".join(b.text for b in msg.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, args=b.input)
            for b in msg.content
            if b.type == "tool_use"
        ]
        tokens_in = msg.usage.input_tokens
        tokens_out = msg.usage.output_tokens
        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=msg.model,
            cost_usd=price(msg.model, tokens_in, tokens_out),
            tool_calls=tool_calls,
        )

    # --- ReAct message-shaping (provider wire format) ---

    @staticmethod
    def assistant_turn(resp: LLMResponse) -> dict:
        content: list[dict] = [{"type": "text", "text": resp.text}] if resp.text else []
        content += [{"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.args}
                    for tc in resp.tool_calls]
        return {"role": "assistant", "content": content}

    @staticmethod
    def tool_results_turn(results, names=None) -> dict:
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": cid, "content": text}
            for cid, text in results]}
