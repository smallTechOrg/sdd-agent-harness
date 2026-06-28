"""Per-model token pricing and cost computation.

Rates are USD per 1,000 tokens. The values below are documented defaults and
are intentionally configurable — adjust to match the current published Gemini
rates for your account/region. What matters for correctness is the math:
``cost = (prompt_tokens * input_per_1k + completion_tokens * output_per_1k) / 1000``.
"""

from observability.events import get_logger

_logger = get_logger("llm.pricing")

# USD per 1,000 tokens. Documented defaults — configurable.
PRICES: dict[str, dict[str, float]] = {
    # Cheap/fast default tier.
    "gemini-2.5-flash": {"input_per_1k": 0.00030, "output_per_1k": 0.00250},
    # Reserved for Phase-4 escalation; placeholder published rates.
    "gemini-2.5-pro": {"input_per_1k": 0.00125, "output_per_1k": 0.01000},
}


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost for a call. Unknown model -> 0.0 (logged), never raises."""
    rates = PRICES.get(model)
    if rates is None:
        _logger.warning("pricing.unknown_model", model=model)
        return 0.0
    prompt_tokens = prompt_tokens or 0
    completion_tokens = completion_tokens or 0
    return (
        prompt_tokens * rates["input_per_1k"]
        + completion_tokens * rates["output_per_1k"]
    ) / 1000.0
