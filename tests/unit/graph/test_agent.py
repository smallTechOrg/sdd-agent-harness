"""Unit tests for the Pandora analysis graph — no real LLM, no env required.

Covers: the graph compiles at import; AgentState carries the expected keys;
the retry/route edge functions behave per spec/agent.md.
"""

import os


# ---------------------------------------------------------------------------
# Compile-without-keys: importing the graph must not need any AGENT_* env.
# ---------------------------------------------------------------------------
def test_graph_compiles_without_env(monkeypatch):
    for var in ("AGENT_GEMINI_API_KEY", "AGENT_ANTHROPIC_API_KEY", "AGENT_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    assert not os.environ.get("AGENT_GEMINI_API_KEY")

    from graph.agent import agentic_ai

    assert agentic_ai is not None
    # Compiled graph exposes invoke/stream.
    assert hasattr(agentic_ai, "invoke")
    assert hasattr(agentic_ai, "stream")


def test_state_has_expected_keys():
    from graph.state import AgentState

    keys = set(AgentState.__annotations__)
    expected = {
        "run_id", "dataset_id", "dataset_path", "profile", "question", "messages",
        "code", "exec_result", "attempts", "last_error",
        "answer_text", "chart_spec", "summary_table",
        "usage", "status", "error",
        # Phase-4 deferred (present but unused):
        "plan", "step_index", "max_steps",
    }
    missing = expected - keys
    assert not missing, f"AgentState missing keys: {missing}"


# ---------------------------------------------------------------------------
# Edge / routing logic — pure functions, no LLM.
# ---------------------------------------------------------------------------
def test_after_validate_valid_goes_to_execute():
    from graph.edges import after_validate

    assert after_validate({"last_error": None, "attempts": 0}) == "execute_code"


def test_after_validate_invalid_first_time_retries():
    from graph.edges import after_validate

    # last_error set, attempts below cap -> regenerate.
    assert after_validate({"last_error": "no imports allowed", "attempts": 0}) == "generate_code"


def test_after_validate_invalid_after_retry_handles_error():
    from graph.edges import after_validate, MAX_ATTEMPTS

    state = {"last_error": "still bad", "attempts": MAX_ATTEMPTS}
    assert after_validate(state) == "handle_error"


def test_after_execute_ok_goes_to_summarise():
    from graph.edges import after_execute

    assert after_execute({"last_error": None, "attempts": 0}) == "summarise"


def test_after_execute_error_first_time_retries():
    from graph.edges import after_execute

    assert after_execute({"last_error": "[runtime_error] boom", "attempts": 0}) == "generate_code"


def test_after_execute_error_after_retry_handles_error():
    from graph.edges import after_execute, MAX_ATTEMPTS

    assert after_execute({"last_error": "[timeout] slow", "attempts": MAX_ATTEMPTS}) == "handle_error"


def test_after_summarise_ok_finalizes_else_handle_error():
    from graph.edges import after_summarise

    assert after_summarise({}) == "finalize"
    assert after_summarise({"error": "summary blew up"}) == "handle_error"


# ---------------------------------------------------------------------------
# Pure nodes (no LLM): handle_error / finalize / usage accumulation.
# ---------------------------------------------------------------------------
def test_handle_error_sets_stuck_with_what_i_tried():
    from graph.nodes import handle_error

    out = handle_error({"last_error": "[runtime_error] KeyError: 'foo'", "code": "result = df['foo']"})
    assert out["status"] == "stuck"
    assert "result = df['foo']" in out["error"]
    assert "KeyError" in out["error"]


def test_finalize_sets_completed():
    from graph.nodes import finalize

    assert finalize({})["status"] == "completed"


def test_usage_accumulates_and_tolerates_none():
    from graph.nodes import _accumulate_usage

    base = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.01}}
    summed = _accumulate_usage(base, {"prompt_tokens": 3, "completion_tokens": 2, "cost_usd": 0.02})
    assert summed["prompt_tokens"] == 13
    assert summed["completion_tokens"] == 7
    assert round(summed["cost_usd"], 4) == 0.03

    # None usage must not error and must leave the running total intact.
    unchanged = _accumulate_usage(base, None)
    assert unchanged["prompt_tokens"] == 10


def test_llm_normaliser_handles_str_tuple_and_object(monkeypatch):
    from graph.nodes import _call_llm
    import graph.nodes as nodes_mod

    captured = {}

    class _FakeClient:
        def call_model(self, prompt, *, system=None):
            return captured["return_value"]

    # monkeypatch auto-restores LLMClient after the test (no cross-test leakage).
    monkeypatch.setattr(nodes_mod, "LLMClient", _FakeClient)

    # plain str
    captured["return_value"] = "just text"
    text, usage = _call_llm("p")
    assert text == "just text" and usage is None

    # (text, usage) tuple
    captured["return_value"] = ("hi", {"prompt_tokens": 4, "completion_tokens": 1, "cost_usd": 0.0})
    text, usage = _call_llm("p")
    assert text == "hi" and usage["prompt_tokens"] == 4

    # object with .text / .usage
    class _Res:
        text = "obj text"
        usage = {"prompt_token_count": 7, "candidates_token_count": 2}

    captured["return_value"] = _Res()
    text, usage = _call_llm("p")
    assert text == "obj text" and usage["prompt_tokens"] == 7 and usage["completion_tokens"] == 2


def test_fence_stripping():
    from graph.nodes import _strip_fences

    assert _strip_fences("```python\nresult = 1\n```") == "result = 1"
    assert _strip_fences("```\nresult = 2\n```") == "result = 2"
    assert _strip_fences("result = 3") == "result = 3"
