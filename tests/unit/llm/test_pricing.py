from llm.pricing import PRICES, cost_for


def test_cost_for_known_model_matches_product():
    rates = PRICES["gemini-2.5-flash"]
    prompt_tokens = 1500
    completion_tokens = 800
    expected = (
        prompt_tokens * rates["input_per_1k"]
        + completion_tokens * rates["output_per_1k"]
    ) / 1000.0
    assert cost_for("gemini-2.5-flash", prompt_tokens, completion_tokens) == expected


def test_cost_for_nonzero_tokens_is_nonzero():
    assert cost_for("gemini-2.5-flash", 1000, 1000) > 0.0


def test_cost_for_unknown_model_returns_zero_and_does_not_raise():
    assert cost_for("does-not-exist", 1000, 1000) == 0.0


def test_cost_for_zero_tokens_is_zero():
    assert cost_for("gemini-2.5-flash", 0, 0) == 0.0


def test_pro_model_priced():
    assert cost_for("gemini-2.5-pro", 1000, 1000) > 0.0
