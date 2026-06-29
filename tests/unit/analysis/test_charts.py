"""Unit tests for choose_chart — deterministic from result shape only."""
from analysis.charts import choose_chart


def test_label_plus_numeric_is_bar():
    rows = [
        {"region": "North", "total_revenue": 1210.0},
        {"region": "South", "total_revenue": 665.0},
        {"region": "East", "total_revenue": 1440.0},
        {"region": "West", "total_revenue": 855.0},
    ]
    schema = [{"name": "region", "type": "VARCHAR"},
              {"name": "revenue", "type": "DOUBLE"}]
    spec = choose_chart("revenue by region", rows, schema)
    assert spec is not None
    assert spec["type"] == "bar"
    assert spec["x"] == "region"
    assert spec["y"] == "total_revenue"
    assert spec["series"] is None
    assert spec["title"]


def test_temporal_label_plus_numeric_is_line():
    rows = [
        {"month": "2024-01-01", "total": 100.0},
        {"month": "2024-02-01", "total": 200.0},
        {"month": "2024-03-01", "total": 300.0},
    ]
    schema = [{"name": "month", "type": "DATE"}, {"name": "total", "type": "DOUBLE"}]
    spec = choose_chart("monthly revenue", rows, schema)
    assert spec is not None
    assert spec["type"] == "line"
    assert spec["x"] == "month"


def test_two_numerics_is_scatter():
    rows = [
        {"quantity": 10, "revenue": 250.0},
        {"quantity": 5, "revenue": 200.0},
        {"quantity": 20, "revenue": 500.0},
    ]
    schema = [{"name": "quantity", "type": "BIGINT"},
              {"name": "revenue", "type": "DOUBLE"}]
    spec = choose_chart("revenue vs quantity", rows, schema)
    assert spec is not None
    assert spec["type"] == "scatter"
    assert spec["x"] == "quantity"
    assert spec["y"] == "revenue"


def test_single_scalar_is_none():
    rows = [{"total_revenue": 3990.0}]
    schema = [{"name": "revenue", "type": "DOUBLE"}]
    assert choose_chart("total revenue", rows, schema) is None


def test_empty_result_is_none():
    assert choose_chart("anything", [], []) is None
    assert choose_chart("anything", None, None) is None


def test_never_raises_on_bad_input():
    # Mixed/None values must not raise; ambiguity returns None gracefully.
    assert choose_chart("x", [{"a": object()}], []) is None
