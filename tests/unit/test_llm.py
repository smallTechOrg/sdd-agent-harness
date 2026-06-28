"""LLM usage extraction, cost math (unit, no network) + guarded real-Gemini checks.

The unit tests construct fake Gemini response objects (no network) to verify the
usage-metadata extraction and cost arithmetic. The integration tests call the
REAL Gemini API using the key from .env (via get_settings); they pytest.skip
only when the key is genuinely absent — never stubbed as the default.
"""
import pytest

from llm.providers.gemini import StreamChunk, Usage, _extract_usage
from llm.cost import compute_cost, cost_from_settings


# --------------------------------------------------------------------------- #
# Fakes mirroring the google-genai response shape (usage_metadata fields).
# --------------------------------------------------------------------------- #
class _FakeUsageMeta:
    def __init__(self, prompt_token_count, candidates_token_count):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count


class _FakeResponse:
    def __init__(self, text, usage_metadata):
        self.text = text
        self.usage_metadata = usage_metadata


# --------------------------------------------------------------------------- #
# Usage extraction (no network)
# --------------------------------------------------------------------------- #
def test_extract_usage_reads_token_counts():
    resp = _FakeResponse("ok", _FakeUsageMeta(prompt_token_count=42, candidates_token_count=7))
    usage = _extract_usage(resp)
    assert isinstance(usage, Usage)
    assert usage.prompt_tokens == 42
    assert usage.completion_tokens == 7


def test_extract_usage_missing_metadata_is_zeroed():
    resp = _FakeResponse("ok", None)
    usage = _extract_usage(resp)
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0


def test_extract_usage_none_token_fields_are_zeroed():
    # Gemini sometimes returns the metadata object with None counts.
    resp = _FakeResponse("ok", _FakeUsageMeta(prompt_token_count=None, candidates_token_count=None))
    usage = _extract_usage(resp)
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0


def test_call_model_with_usage_extracts_from_fake_response(monkeypatch):
    """call_model_with_usage returns (text, Usage) read from the SDK response."""
    from llm.providers import gemini as gem

    monkeypatch.setattr(gem.genai, "Client", lambda *a, **k: object())
    provider = gem.GeminiProvider(api_key="fake", model="gemini-2.5-flash")

    captured = {}

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["system"] = getattr(config, "system_instruction", None) if config else None
            return _FakeResponse("hello", _FakeUsageMeta(prompt_token_count=11, candidates_token_count=3))

    class _FakeClient:
        models = _FakeModels()

    provider._client = _FakeClient()

    text, usage = provider.call_model_with_usage("hi", system="be terse")
    assert text == "hello"
    assert usage.prompt_tokens == 11
    assert usage.completion_tokens == 3
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["contents"] == "hi"
    assert captured["system"] == "be terse"


def test_call_model_returns_text_only(monkeypatch):
    """The base call_model still returns plain text via call_model_with_usage."""
    from llm.providers import gemini as gem

    monkeypatch.setattr(gem.genai, "Client", lambda *a, **k: object())
    provider = gem.GeminiProvider(api_key="fake", model="gemini-2.5-flash")

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            return _FakeResponse("plain", _FakeUsageMeta(5, 1))

    class _FakeClient:
        models = _FakeModels()

    provider._client = _FakeClient()
    assert provider.call_model("hi") == "plain"


def test_stream_model_yields_chunks_and_final_usage(monkeypatch):
    """stream_model yields StreamChunk(text, usage); last non-None usage is final."""
    from llm.providers import gemini as gem

    monkeypatch.setattr(gem.genai, "Client", lambda *a, **k: object())
    provider = gem.GeminiProvider(api_key="fake", model="gemini-2.5-flash")

    class _FakeChunk:
        def __init__(self, text, usage_metadata):
            self.text = text
            self.usage_metadata = usage_metadata

    class _FakeModels:
        def generate_content_stream(self, *, model, contents, config):
            # mid-stream chunks have no usage; final chunk carries cumulative usage
            yield _FakeChunk("One, ", None)
            yield _FakeChunk("two, three.", _FakeUsageMeta(prompt_token_count=10, candidates_token_count=6))

    class _FakeClient:
        models = _FakeModels()

    provider._client = _FakeClient()

    chunks = list(provider.stream_model("count", system=None))
    assert all(isinstance(c, StreamChunk) for c in chunks)
    text = "".join(c.text for c in chunks)
    assert text == "One, two, three."

    final_usage = None
    for c in chunks:
        if c.usage is not None:
            final_usage = c.usage
    assert final_usage is not None
    assert final_usage.prompt_tokens == 10
    assert final_usage.completion_tokens == 6


# --------------------------------------------------------------------------- #
# Cost math (no network)
# --------------------------------------------------------------------------- #
def test_compute_cost_one_million_each():
    # 1M input @ 0.10 + 1M output @ 0.40 = 0.10 + 0.40 = 0.50
    assert compute_cost(1_000_000, 1_000_000, price_input_per_m=0.10, price_output_per_m=0.40) == 0.50


def test_compute_cost_zero_tokens():
    assert compute_cost(0, 0, price_input_per_m=0.10, price_output_per_m=0.40) == 0.0


def test_compute_cost_asymmetric_and_rounded():
    # 500k input @ 0.10 = 0.05 ; 250k output @ 0.40 = 0.10 ; total 0.15
    assert compute_cost(500_000, 250_000, price_input_per_m=0.10, price_output_per_m=0.40) == 0.15


def test_compute_cost_rounds_to_six_dp():
    # 1 input token @ 0.10/M = 0.0000001 -> rounds to 0.0 at 6dp
    assert compute_cost(1, 0, price_input_per_m=0.10, price_output_per_m=0.40) == 0.0
    # 7 output tokens @ 0.40/M = 0.0000028 -> rounds to 0.000003 at 6dp
    assert compute_cost(0, 7, price_input_per_m=0.40, price_output_per_m=0.40) == 0.000003


def test_cost_from_settings_uses_default_pricing(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.delenv("AGENT_PRICE_INPUT_PER_M", raising=False)
    monkeypatch.delenv("AGENT_PRICE_OUTPUT_PER_M", raising=False)
    import config.settings as m
    m._settings = None
    s = m.get_settings()
    assert s.price_input_per_m == 0.10
    assert s.price_output_per_m == 0.40
    assert cost_from_settings(1_000_000, 1_000_000) == 0.50


def test_cost_from_settings_honors_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("AGENT_PRICE_INPUT_PER_M", "1.00")
    monkeypatch.setenv("AGENT_PRICE_OUTPUT_PER_M", "2.00")
    import config.settings as m
    m._settings = None
    assert cost_from_settings(1_000_000, 1_000_000) == 3.0


# --------------------------------------------------------------------------- #
# Real-Gemini integration (guarded by key presence — never stubbed)
# --------------------------------------------------------------------------- #
@pytest.fixture
def _require_gemini_key():
    from config.settings import get_settings
    s = get_settings()
    if not s.gemini_api_key:
        pytest.skip("No AGENT_GEMINI_API_KEY set in .env — skipping real-Gemini integration")


def test_real_call_model_with_usage(_require_gemini_key):
    """Real Gemini call returns non-empty text and positive prompt tokens."""
    from llm.client import LLMClient, Usage

    client = LLMClient()
    text, usage = client.call_model_with_usage("Reply with the single word: ok")
    assert isinstance(text, str) and text.strip() != ""
    assert isinstance(usage, Usage)
    assert usage.prompt_tokens > 0
    assert usage.completion_tokens > 0


def test_real_stream_model_captures_final_usage(_require_gemini_key):
    """Real streamed call yields text chunks and a captured final usage."""
    from llm.client import LLMClient

    client = LLMClient()
    collected = []
    final_usage = None
    for chunk in client.stream_model("Count from one to three."):
        collected.append(chunk.text)
        if chunk.usage is not None:
            final_usage = chunk.usage

    full = "".join(collected)
    assert full.strip() != ""
    assert final_usage is not None
    assert final_usage.prompt_tokens > 0
    assert final_usage.completion_tokens > 0
