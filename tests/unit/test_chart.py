"""Unit tests for the chart-spec builder (no LLM)."""

from __future__ import annotations

import pytest

from datachat.data.chart import ChartError, build_chart

TABLE = {"columns": ["region", "total"], "rows": [["west", 150], ["east", 275]]}


def test_build_bar_chart():
    spec = build_chart(TABLE, "bar", "region", "total", "Sales by region")
    assert spec["type"] == "bar"
    assert spec["x"] == "region" and spec["y"] == "total"
    assert spec["data"] == [{"x": "west", "y": 150}, {"x": "east", "y": 275}]


@pytest.mark.parametrize("bad_type", ["scatter", "", "histogram"])
def test_rejects_unknown_type(bad_type):
    with pytest.raises(ChartError):
        build_chart(TABLE, bad_type, "region", "total", "t")


def test_rejects_unknown_column():
    with pytest.raises(ChartError, match="x_column"):
        build_chart(TABLE, "bar", "nope", "total", "t")
    with pytest.raises(ChartError, match="y_column"):
        build_chart(TABLE, "bar", "region", "nope", "t")


def test_rejects_empty_result():
    with pytest.raises(ChartError):
        build_chart(None, "bar", "a", "b", "t")
    with pytest.raises(ChartError):
        build_chart({"columns": ["a", "b"], "rows": []}, "bar", "a", "b", "t")
