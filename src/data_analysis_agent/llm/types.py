from dataclasses import dataclass


# Approximate OpenRouter pricing per 1M tokens (USD).
# Used only when the provider doesn't return cost directly.
_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "google/gemini-2.5-flash":       (0.15,  0.60),
    "google/gemini-2.5-pro":         (1.25,  5.00),
    "google/gemini-2.0-flash":       (0.10,  0.40),
    "openai/gpt-4o-mini":            (0.15,  0.60),
    "openai/gpt-4o":                 (2.50, 10.00),
    "anthropic/claude-3-5-haiku":    (0.80,  4.00),
    "anthropic/claude-sonnet-4-5":   (3.00, 15.00),
    "meta-llama/llama-3.3-70b-instruct": (0.06, 0.20),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate USD cost from token counts, or ``None`` if the model is unpriced."""
    key = model.split(":")[0]  # strip provider suffix variants like ":nitro"
    pricing = _PRICING_PER_M.get(key)
    if pricing is None:
        return None
    in_price, out_price = pricing
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
