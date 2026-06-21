"""FR-001 multi-chart dashboard criterion.

Gate command: uv run --extra dev pytest tests/test_dashboard_fr.py -v
"""
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.runner import run_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tc(name: str, args: dict, tid: str):
    return {"id": tid, "name": name, "args": args, "type": "tool_call"}


def _tool_msgs(messages) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


# ---------------------------------------------------------------------------
# Minimal chart spec fixtures
# ---------------------------------------------------------------------------

_SPEC_A = json.dumps({
    "data": [{"type": "bar", "x": ["A", "B", "C"], "y": [10, 20, 30], "name": "Series A"}],
    "layout": {"title": "Chart A", "xaxis": {"title": "X"}, "yaxis": {"title": "Y"}},
})

_SPEC_B = json.dumps({
    "data": [{"type": "pie", "labels": ["X", "Y", "Z"], "values": [40, 35, 25]}],
    "layout": {"title": "Chart B"},
})


# ---------------------------------------------------------------------------
# FR criterion 1: dashboard response returns multiple Plotly configs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_response_returns_multiple_chart_specs():
    """WHEN agent returns dashboard_specs, run_agent SHALL return a list with 2+ valid Plotly configs."""

    class _DashboardModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            # Single-step fake: immediately call finish with two chart specs
            return AIMessage(content="", tool_calls=[
                _tc("finish", {
                    "answer": "Here is your dashboard with two charts.",
                    "dashboard_specs": [_SPEC_A, _SPEC_B],
                }, "d1")
            ])

    result = await run_agent(
        goal="Show me a dashboard with two charts",
        model=_DashboardModel(),
    )

    assert result["status"] == "completed"
    assert result["answer"] == "Here is your dashboard with two charts."

    specs = result.get("dashboard_specs")
    assert isinstance(specs, list), f"dashboard_specs must be a list, got {type(specs)}"
    assert len(specs) >= 2, f"Expected at least 2 specs, got {len(specs)}"

    for i, spec_raw in enumerate(specs):
        parsed = json.loads(spec_raw) if isinstance(spec_raw, str) else spec_raw
        assert isinstance(parsed, dict), f"spec[{i}] must be a dict"
        assert "data" in parsed, f"spec[{i}] must have 'data' key"


# ---------------------------------------------------------------------------
# FR criterion 2: single chart_spec path still works after dashboard changes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_chart_response_still_works():
    """Regression: single chart_spec path still works after dashboard changes."""

    class _SingleChartModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="", tool_calls=[
                _tc("finish", {
                    "answer": "Here is your single chart.",
                    "chart_spec": _SPEC_A,
                }, "s1")
            ])

    result = await run_agent(
        goal="Show me a bar chart",
        model=_SingleChartModel(),
    )

    assert result["status"] == "completed"
    assert result["answer"] == "Here is your single chart."

    # Single chart path
    assert result.get("chart_spec") is not None, "chart_spec must be present"
    parsed = json.loads(result["chart_spec"]) if isinstance(result["chart_spec"], str) else result["chart_spec"]
    assert "data" in parsed, "chart_spec must have 'data' key"

    # dashboard_specs must default to empty list (not None)
    specs = result.get("dashboard_specs")
    assert isinstance(specs, list), f"dashboard_specs must be a list even when absent, got {type(specs)}"
    assert len(specs) == 0, f"dashboard_specs must be empty for single-chart response, got {specs}"


# ---------------------------------------------------------------------------
# FR criterion 3: dashboard_specs defaults to [] when finish omits it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_specs_defaults_to_empty_list_when_omitted():
    """WHEN finish is called without dashboard_specs, result SHALL have dashboard_specs=[]."""

    class _NoSpecModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="", tool_calls=[
                _tc("finish", {
                    "answer": "Plain prose answer, no charts.",
                }, "n1")
            ])

    result = await run_agent(
        goal="What is in this dataset?",
        model=_NoSpecModel(),
    )

    assert result["status"] == "completed"
    specs = result.get("dashboard_specs")
    assert specs == [], f"dashboard_specs must be [] when omitted from finish, got {specs!r}"
