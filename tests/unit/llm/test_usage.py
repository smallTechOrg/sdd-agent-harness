import pytest

from config.settings import get_settings

from llm.pricing import cost_for
from llm.usage import (
    LLMResult,
    Usage,
    accumulate,
    usage_from_dict,
    usage_from_gemini,
)


class _FakeMetadata:
    def __init__(self, prompt, candidates):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates


class _FakeResponse:
    def __init__(self, prompt, candidates):
        self.usage_metadata = _FakeMetadata(prompt, candidates)
        self.text = "hello"


def test_usage_from_gemini_reads_tokens_and_cost():
    resp = _FakeResponse(prompt=1200, candidates=300)
    usage = usage_from_gemini(resp, "gemini-2.5-flash")
    assert usage.prompt_tokens == 1200
    assert usage.completion_tokens == 300
    assert usage.model == "gemini-2.5-flash"
    assert usage.cost_usd == cost_for("gemini-2.5-flash", 1200, 300)
    assert usage.cost_usd > 0.0


def test_usage_from_gemini_missing_metadata_is_zero_not_crash():
    class _NoMeta:
        usage_metadata = None

    usage = usage_from_gemini(_NoMeta(), "gemini-2.5-flash")
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.cost_usd == 0.0


def test_usage_from_gemini_none_token_fields_are_zero():
    resp = _FakeResponse(prompt=None, candidates=None)
    usage = usage_from_gemini(resp, "gemini-2.5-flash")
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0


def test_usage_add_sums_both_calls():
    a = Usage(prompt_tokens=100, completion_tokens=50, cost_usd=0.001, model="m")
    b = Usage(prompt_tokens=200, completion_tokens=70, cost_usd=0.002, model="m")
    total = a.add(b)
    assert total.prompt_tokens == 300
    assert total.completion_tokens == 120
    assert total.cost_usd == pytest.approx(0.003)


def test_accumulate_sums_many():
    a = Usage(prompt_tokens=10, completion_tokens=5, cost_usd=0.1, model="m")
    b = Usage(prompt_tokens=20, completion_tokens=6, cost_usd=0.2, model="m")
    c = Usage(prompt_tokens=30, completion_tokens=7, cost_usd=0.3, model="m")
    total = accumulate(a, b, c)
    assert total.prompt_tokens == 60
    assert total.completion_tokens == 18
    assert total.cost_usd == pytest.approx(0.6)


def test_usage_add_with_none_is_identity():
    a = Usage(prompt_tokens=10, completion_tokens=5, cost_usd=0.1, model="m")
    assert a.add(None) is a


def test_usage_from_dict_provider_shape():
    usage = usage_from_dict(
        {"prompt_tokens": 500, "completion_tokens": 250, "model": "gemini-2.5-flash"},
        "fallback",
    )
    assert usage.prompt_tokens == 500
    assert usage.completion_tokens == 250
    assert usage.model == "gemini-2.5-flash"
    assert usage.cost_usd == cost_for("gemini-2.5-flash", 500, 250)


def test_llm_result_str_equals_text_and_carries_usage():
    usage = Usage(prompt_tokens=1, completion_tokens=2, cost_usd=0.0, model="m")
    result = LLMResult(text="the answer", usage=usage)
    assert str(result) == "the answer"
    assert result.text == "the answer"
    assert result.usage is usage


@pytest.mark.skipif(
    not get_settings().gemini_api_key,
    reason="no AGENT_GEMINI_API_KEY configured",
)
def test_real_gemini_call_returns_nonzero_prompt_tokens():
    from llm.client import LLMClient

    result = LLMClient().call_model("Reply with the single word: ok")
    assert isinstance(result, LLMResult)
    assert str(result)  # non-empty text
    assert result.usage.prompt_tokens > 0
    assert result.usage.cost_usd > 0.0
