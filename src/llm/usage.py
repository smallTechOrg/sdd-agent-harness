"""Token usage extraction and accumulation.

A ``Usage`` captures the tokens and computed dollar cost for one (or, after
``add``/``accumulate``, several) LLM call(s). ``LLMResult`` is the return type
of ``LLMClient.call_model`` — it behaves like the answer text (``str(result)``)
while carrying the ``Usage`` alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llm.pricing import cost_for


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str

    def add(self, other: "Usage | None") -> "Usage":
        """Sum two Usages (e.g. the code-gen + summarise calls for one question)."""
        if other is None:
            return self
        return Usage(
            prompt_tokens=(self.prompt_tokens or 0) + (other.prompt_tokens or 0),
            completion_tokens=(self.completion_tokens or 0)
            + (other.completion_tokens or 0),
            cost_usd=(self.cost_usd or 0.0) + (other.cost_usd or 0.0),
            # Model name carries the last call's model; same model in practice.
            model=other.model or self.model,
        )


def accumulate(*usages: "Usage | None") -> Usage:
    """Sum any number of Usages into one. Empty -> zero Usage."""
    total = Usage(prompt_tokens=0, completion_tokens=0, cost_usd=0.0, model="")
    for u in usages:
        total = total.add(u)
    return total


def _read_token(metadata, *names: str) -> int:
    for name in names:
        value = getattr(metadata, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def usage_from_gemini(response, model: str) -> Usage:
    """Build a ``Usage`` from a google-genai response (defensive about shape).

    Reads ``response.usage_metadata.prompt_token_count`` and
    ``.candidates_token_count``; missing/None -> 0. Never raises on a
    well-formed-but-incomplete response.
    """
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        prompt_tokens = 0
        completion_tokens = 0
    else:
        prompt_tokens = _read_token(metadata, "prompt_token_count")
        completion_tokens = _read_token(
            metadata, "candidates_token_count", "completion_token_count"
        )
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_for(model, prompt_tokens, completion_tokens),
        model=model,
    )


def usage_from_dict(usage_dict: dict | None, model: str) -> Usage:
    """Build a ``Usage`` from the provider's ``{prompt_tokens, completion_tokens, model}``."""
    usage_dict = usage_dict or {}
    prompt_tokens = int(usage_dict.get("prompt_tokens") or 0)
    completion_tokens = int(usage_dict.get("completion_tokens") or 0)
    resolved_model = usage_dict.get("model") or model
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_for(resolved_model, prompt_tokens, completion_tokens),
        model=resolved_model,
    )


@dataclass
class LLMResult:
    """Return type of ``LLMClient.call_model``.

    Behaves like the answer text via ``str(result)`` / ``__str__`` while
    carrying token usage. Consumers may use ``result.text`` and ``result.usage``
    directly, or treat ``str(result)`` as the text.
    """

    text: str
    usage: Usage

    def __str__(self) -> str:
        return self.text
