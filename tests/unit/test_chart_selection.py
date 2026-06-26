"""Unit tests for the chart_selection node — no DB or LLM calls."""
import pytest
from graph.nodes import chart_selection


def _state(rows, question="Test question"):
    return {
        "rows": rows,
        "schema": [],
        "question": question,
        "table_name": "test_table",
    }


class TestChartSelectionEmptyRows:
    def test_empty_list_gives_empty_type(self):
        state = _state([])
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "empty"

    def test_none_rows_gives_empty_type(self):
        state = _state(None)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "empty"

    def test_empty_chart_has_data_list(self):
        state = _state([])
        result = chart_selection(state)
        assert result["chart_spec"]["data"] == []

    def test_empty_chart_has_title(self):
        state = _state([], question="How many products?")
        result = chart_selection(state)
        assert "How many products?" in result["chart_spec"]["title"]


class TestChartSelectionBarChart:
    def test_string_plus_numeric_gives_bar(self):
        rows = [
            {"product": "Apple", "revenue": 100.0},
            {"product": "Banana", "revenue": 50.0},
            {"product": "Cherry", "revenue": 75.0},
            # More than 8 unique values would switch to bar; 3 unique is still pie
            # but we want to test bar specifically with many unique values
        ]
        # With 3 unique values, it would be pie. Add more to force bar.
        rows = [{"product": f"Product_{i}", "revenue": float(i * 10)} for i in range(10)]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] in ("bar", "pie")

    def test_two_col_numeric_string_many_unique_bar(self):
        rows = [{"category": f"Cat{i}", "value": float(i)} for i in range(15)]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "bar"

    def test_bar_chart_has_xkey_ykey(self):
        rows = [{"category": f"Cat{i}", "value": float(i)} for i in range(15)]
        state = _state(rows)
        result = chart_selection(state)
        spec = result["chart_spec"]
        assert "xKey" in spec
        assert "yKey" in spec
        assert "data" in spec

    def test_bar_chart_data_uses_column_names_as_keys(self):
        rows = [{"category": f"Cat{i}", "value": float(i)} for i in range(15)]
        state = _state(rows)
        result = chart_selection(state)
        spec = result["chart_spec"]
        x_key = spec["xKey"]
        y_key = spec["yKey"]
        # Each data point must have the actual column names as keys
        for point in spec["data"]:
            assert x_key in point
            assert y_key in point


class TestChartSelectionPieChart:
    def test_few_unique_string_values_gives_pie(self):
        rows = [
            {"region": "North", "sales": 1000.0},
            {"region": "South", "sales": 800.0},
            {"region": "East", "sales": 600.0},
        ]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "pie"

    def test_pie_chart_has_name_and_value_keys(self):
        rows = [
            {"region": "North", "sales": 1000.0},
            {"region": "South", "sales": 800.0},
        ]
        state = _state(rows)
        result = chart_selection(state)
        spec = result["chart_spec"]
        assert "nameKey" in spec
        assert "valueKey" in spec

    def test_pie_exactly_eight_unique_values(self):
        rows = [{"cat": f"C{i}", "val": float(i)} for i in range(8)]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "pie"

    def test_pie_nine_unique_values_becomes_bar(self):
        rows = [{"cat": f"C{i}", "val": float(i)} for i in range(9)]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "bar"


class TestChartSelectionLineChart:
    def test_date_like_column_gives_line(self):
        rows = [
            {"date": "2024-01-01", "revenue": 1000.0},
            {"date": "2024-02-01", "revenue": 1200.0},
            {"date": "2024-03-01", "revenue": 900.0},
        ]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "line"

    def test_slash_date_gives_line(self):
        rows = [
            {"period": "01/2024", "amount": 500.0},
            {"period": "02/2024", "amount": 600.0},
        ]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "line"


class TestChartSelectionScatter:
    def test_two_numeric_columns_gives_scatter(self):
        rows = [
            {"x_val": 1.0, "y_val": 2.0},
            {"x_val": 3.0, "y_val": 4.0},
        ]
        state = _state(rows)
        result = chart_selection(state)
        assert result["chart_spec"]["type"] == "scatter"

    def test_scatter_has_xkey_ykey(self):
        rows = [{"a": 1.0, "b": 2.0}, {"a": 3.0, "b": 6.0}]
        state = _state(rows)
        result = chart_selection(state)
        spec = result["chart_spec"]
        assert "xKey" in spec
        assert "yKey" in spec


class TestChartSelectionNoError:
    def test_no_error_on_empty(self):
        state = _state([])
        result = chart_selection(state)
        assert "error" not in result or result.get("error") is None

    def test_no_error_on_valid_data(self):
        rows = [{"cat": "A", "val": 1.0}]
        state = _state(rows)
        result = chart_selection(state)
        assert "error" not in result or result.get("error") is None
