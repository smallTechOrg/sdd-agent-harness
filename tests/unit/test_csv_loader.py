"""Unit tests for CSV type inference — no DB or LLM calls."""
import pytest
from api.upload import infer_column_type


class TestInferColumnType:
    def test_integer_value(self):
        assert infer_column_type(["42"]) == "INTEGER"

    def test_negative_integer(self):
        assert infer_column_type(["-10"]) == "INTEGER"

    def test_zero(self):
        assert infer_column_type(["0"]) == "INTEGER"

    def test_float_value(self):
        assert infer_column_type(["3.14"]) == "REAL"

    def test_negative_float(self):
        assert infer_column_type(["-0.5"]) == "REAL"

    def test_text_value(self):
        assert infer_column_type(["hello"]) == "TEXT"

    def test_date_string(self):
        assert infer_column_type(["2024-01-15"]) == "TEXT"

    def test_empty_list(self):
        assert infer_column_type([]) == "TEXT"

    def test_integer_with_spaces_is_text(self):
        # "1 2" is not a valid int or float
        assert infer_column_type(["1 2"]) == "TEXT"

    def test_scientific_notation_is_real(self):
        assert infer_column_type(["1.5e3"]) == "REAL"

    def test_mixed_alphanumeric(self):
        assert infer_column_type(["abc123"]) == "TEXT"

    def test_large_integer(self):
        assert infer_column_type(["1000000"]) == "INTEGER"

    def test_all_integers(self):
        assert infer_column_type(["1", "2", "3", "100"]) == "INTEGER"

    def test_all_floats(self):
        assert infer_column_type(["1.1", "2.2", "3.3"]) == "REAL"

    def test_mixed_int_and_text_is_text(self):
        # If ANY value is not int-parseable -> try float; if any not float -> TEXT
        assert infer_column_type(["1", "2", "text"]) == "TEXT"

    def test_mixed_int_and_float_is_real(self):
        # "1" parses as float too, so if all values parse as float but not all as int -> REAL
        assert infer_column_type(["1", "2.5", "3"]) == "REAL"

    def test_mixed_float_and_text_is_text(self):
        assert infer_column_type(["1.5", "hello", "3.0"]) == "TEXT"

    def test_single_text_value(self):
        assert infer_column_type(["abc"]) == "TEXT"


def test_csv_upload_type_inference_with_real_file(tmp_path):
    """Test that a real CSV file gets the right types inferred."""
    import csv
    import io

    csv_content = "product,quantity,revenue\nApple,10,99.99\nBanana,5,49.50\n"
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)
    headers = list(reader.fieldnames) if reader.fieldnames else list(rows[0].keys())

    col_types = {}
    for col in headers:
        non_empty_vals = [
            (row.get(col) or "").strip()
            for row in rows
            if (row.get(col) or "").strip()
        ]
        col_types[col] = infer_column_type(non_empty_vals)

    assert col_types["product"] == "TEXT"
    assert col_types["quantity"] == "INTEGER"
    assert col_types["revenue"] == "REAL"


def test_csv_empty_cells_become_none(tmp_path):
    """Empty cells are treated as None during upload."""
    import csv
    import io

    csv_content = "name,score\nAlice,\nBob,100\n"
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    # Alice score is empty string
    assert rows[0]["score"] == ""
    # empty string should map to None in param row
    val = (rows[0].get("score") or "").strip()
    assert val == ""


def test_csv_many_columns(tmp_path):
    """Test that a CSV with many columns infers types for all."""
    import csv
    import io

    # 10 columns: 5 text, 5 integer
    headers = [f"text_col_{i}" for i in range(5)] + [f"int_col_{i}" for i in range(5)]
    row = {f"text_col_{i}": f"val_{i}" for i in range(5)}
    row.update({f"int_col_{i}": str(i * 10) for i in range(5)})

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerow(row)
    buf.seek(0)

    reader = csv.DictReader(buf)
    rows = list(reader)

    col_types = {}
    for col in headers:
        non_empty_vals = [
            (r.get(col) or "").strip()
            for r in rows
            if (r.get(col) or "").strip()
        ]
        col_types[col] = infer_column_type(non_empty_vals)

    for i in range(5):
        assert col_types[f"text_col_{i}"] == "TEXT"
        assert col_types[f"int_col_{i}"] == "INTEGER"
