"""Token -> USD cost computation for LLM calls.

Pricing is per *million* tokens, configured via settings:
  price_input_per_m  (AGENT_PRICE_INPUT_PER_M,  default 0.10)
  price_output_per_m (AGENT_PRICE_OUTPUT_PER_M, default 0.40)
"""

from config.settings import get_settings

_DECIMALS = 6


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    price_input_per_m: float,
    price_output_per_m: float,
) -> float:
    """USD cost for a call given token counts and per-million-token prices.

    cost = prompt/1e6 * price_input + completion/1e6 * price_output
    Rounded to 6 decimal places.
    """
    cost = (
        (prompt_tokens / 1_000_000.0) * price_input_per_m
        + (completion_tokens / 1_000_000.0) * price_output_per_m
    )
    return round(cost, _DECIMALS)


def cost_from_settings(prompt_tokens: int, completion_tokens: int) -> float:
    """compute_cost using the pricing fields from get_settings()."""
    s = get_settings()
    return compute_cost(
        prompt_tokens,
        completion_tokens,
        price_input_per_m=s.price_input_per_m,
        price_output_per_m=s.price_output_per_m,
    )
