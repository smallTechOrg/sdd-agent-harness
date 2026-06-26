"""Phase-2 SQL mode integration tests — mirror all Phase-1 pandas tests against the REAL Gemini API.

Covers the four analytical shapes (group-by, filter+aggregate, sort+top-N,
single-value) and the two failure guards (malformed upload, unanswerable question)
in SQL mode. Expected results are computed with pandas and asserted exactly,
so the result numbers are identical between pandas and SQL modes; the generated
code differs (SQL vs pandas).

Requires ``AGENT_GEMINI_API_KEY`` in ``.env`` (the ``_require_llm_key`` fixture
skips otherwise; the gate runs with the key present, so these execute for real).
"""
import json
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.usefixtures("_require_llm_key")

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _csv_text(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _sales_df() -> pd.DataFrame:
    return pd.read_csv(_FIXTURES / "sales.csv")


def _post_sql(api_client, csv_text: str, question: str) -> dict:
    """POST /runs with mode='sql'."""
    r = api_client.post(
        "/runs",
        json={"csv_text": csv_text, "question": question, "mode": "sql"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    return body["data"]


def _table_cell_strings(result_table: dict) -> list[str]:
    """Flatten a result_table's cells to their string forms for value membership checks."""
    if not result_table:
        return []
    return [str(cell) for row in result_table["rows"] for cell in row]


# Small-integer spellings 0..20 plus the round tens, so a count the model writes
# as a WORD ("six") is accepted alongside the digit ("6"). Real-LLM integration
# tests must tolerate phrasing variation while still proving the COMPUTED VALUE.
_NUMBER_WORDS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
    17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
    30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
    80: "eighty", 90: "ninety", 100: "hundred",
}


def _value_forms(n: int) -> list[str]:
    """All acceptable surface forms of an integer: digit, thousands-grouped, and
    (for small/round values) the spelled-out English word."""
    forms = [str(n), f"{n:,}"]
    if n in _NUMBER_WORDS:
        forms.append(_NUMBER_WORDS[n])
    return forms


def _haystack(data: dict) -> str:
    """Lower-cased searchable text covering every field the app uses to surface a
    scalar: answer, explanation, generated_code, and any result_table cells."""
    parts = [
        data.get("answer") or "",
        data.get("explanation") or "",
        data.get("generated_code") or "",
        " ".join(_table_cell_strings(data.get("result_table"))),
    ]
    return " ".join(parts).lower()


def _answer_text(data: dict) -> str:
    """The lower-cased prose the model wrote to STATE its result (answer +
    explanation). This is where a count/scalar is verbalised."""
    return ((data.get("answer") or "") + " " + (data.get("explanation") or "")).lower()


def _contains_value(text: str, n: int) -> bool:
    """True if integer ``n`` appears in ``text`` as a digit (optionally thousands-
    grouped) or, for small/round values, as its spelled-out English word."""
    return any(form.lower() in text for form in _value_forms(n))


def _assert_scalar_value(data: dict, expected: int, *, wrong_neighbors: tuple[int, ...] = ()) -> None:
    """Assert the correct computed scalar appears (digit OR spelled-out word) across
    the fields the app populates, and that obviously-wrong neighbour values are NOT
    the stated answer."""
    hay = _haystack(data)
    assert _contains_value(hay, expected), (
        f"expected value {expected} (as digit or word) in answer/explanation/code/table; got {data}"
    )
    # The stated result must not BE a wrong neighbour. Check the prose the model
    # wrote (answer/explanation), not generated_code (which carries incidental
    # digits like row counts).
    answer = _answer_text(data)
    if _contains_value(answer, expected):
        for wrong in wrong_neighbors:
            assert not _contains_value(answer, wrong), (
                f"wrong neighbour value {wrong} appeared in the stated answer; got {data}"
            )


# --- Analytical shape 1: group-by aggregation (SQL mode) ---


def test_sql_group_by_region_highest_first(api_client):
    """Group-by aggregation in SQL mode: total sales by region, highest first."""
    df = _sales_df()
    expected = df.groupby("region")["sales"].sum().sort_values(ascending=False)
    expected_order = list(expected.index)            # ['East','West','North','South']
    expected_totals = [int(v) for v in expected.values]  # [590, 530, 520, 380]

    data = _post_sql(api_client, _csv_text("sales.csv"), "What were total sales by region, highest first?")

    assert data["status"] == "completed", data.get("error")
    assert data["error"] is None
    assert data["mode"] == "sql", "mode should be 'sql'"

    # Show-its-work: real generated SQL (not pandas)
    assert data["generated_code"]
    code_upper = data["generated_code"].upper()
    assert "SELECT" in code_upper, f"SQL code should start with SELECT: {data['generated_code']}"
    assert "GROUP BY" in code_upper, f"SQL code should have GROUP BY: {data['generated_code']}"

    table = data["result_table"]
    assert table is not None, "a group-by must return a result table"
    cols = [c.lower() for c in table["columns"]]
    assert "region" in cols

    region_idx = cols.index("region")
    # Find the sales column (the other numeric column).
    sales_idx = next(i for i, c in enumerate(cols) if c != "region")

    got = [(str(row[region_idx]), int(row[sales_idx])) for row in table["rows"]]
    # Correct per-region sums...
    assert dict(got) == dict(zip(expected_order, expected_totals))
    # ...in descending order (highest first).
    assert [r for r, _ in got] == expected_order


# --- Analytical shape 2: filter + aggregate (SQL mode) ---


def test_sql_filter_then_aggregate_shipped_late_count(api_client):
    """Filter + aggregate in SQL mode: count of orders shipped late."""
    df = _sales_df()
    expected = int((df["shipped_late"] == True).sum())  # noqa: E712 — exact 6

    data = _post_sql(api_client, _csv_text("sales.csv"), "How many orders shipped late?")

    assert data["status"] == "completed", data.get("error")
    assert data["mode"] == "sql"
    assert data["generated_code"], "show-its-work: a count must expose generated code"
    assert "SELECT" in data["generated_code"].upper()

    # This is a SCALAR count: real Gemini may phrase it as the word "six".
    # Accept digit-or-word, but reject the adjacent wrong counts 5 and 7.
    _assert_scalar_value(data, expected, wrong_neighbors=(5, 7))


def test_sql_filter_total_sales_for_one_region(api_client):
    """Filter + aggregate in SQL mode: total sales for one region."""
    df = _sales_df()
    expected = int(df[df["region"] == "North"]["sales"].sum())  # 520

    data = _post_sql(api_client, _csv_text("sales.csv"), "What were the total sales for the North region?")

    assert data["status"] == "completed", data.get("error")
    assert data["mode"] == "sql"
    assert data["generated_code"], "show-its-work: a scalar aggregate must expose generated code"

    # Scalar total surfaces in the answer text. Reject the other regions' totals.
    _assert_scalar_value(data, expected, wrong_neighbors=(590, 530, 380, 2020))


# --- Analytical shape 3: sort + top-N (SQL mode) ---


def test_sql_top_n_products_by_sales(api_client):
    """Top-N in SQL mode: top 3 products by total sales."""
    df = _sales_df()
    ranked = df.groupby("product")["sales"].sum().sort_values(ascending=False)
    expected_top3 = list(ranked.index)[:3]  # ['Gadget','Widget','Gizmo']

    data = _post_sql(api_client, _csv_text("sales.csv"), "What are the top 3 products by total sales, highest first?")

    assert data["status"] == "completed", data.get("error")
    assert data["mode"] == "sql"
    assert data["generated_code"]
    assert "SELECT" in data["generated_code"].upper()

    table = data["result_table"]
    assert table is not None, "top-N must return a result table"
    product_idx = next(
        (i for i, c in enumerate(table["columns"]) if c.lower() == "product"), 0
    )
    got_products = [str(row[product_idx]) for row in table["rows"]]
    assert got_products[:3] == expected_top3, f"expected top-3 {expected_top3}, got {got_products}"


# --- Analytical shape 4: single-value aggregate (SQL mode) ---


def test_sql_single_value_total_sales(api_client):
    """Single-value aggregate in SQL mode: total of the sales column."""
    df = _sales_df()
    expected = int(df["sales"].sum())  # 2020

    data = _post_sql(api_client, _csv_text("sales.csv"), "What is the total of the sales column across all rows?")

    assert data["status"] == "completed", data.get("error")
    assert data["mode"] == "sql"
    assert data["generated_code"], "show-its-work: a scalar aggregate must expose generated code"
    assert "SELECT" in data["generated_code"].upper()

    # Single-value aggregate surfaces in the answer text. Reject the per-region subtotals.
    _assert_scalar_value(data, expected, wrong_neighbors=(590, 530, 520, 380))


# --- Failure guard 1: malformed / non-CSV upload (SQL mode) ---


def test_sql_malformed_upload_fails_gracefully(api_client):
    """Malformed CSV in SQL mode must fail gracefully."""
    malformed = "this is not a csv\nit has\nrandom,ragged\nlines,1,2,3,4,5\nx"

    data = _post_sql(api_client, malformed, "What were total sales by region?")

    assert data["status"] == "failed", f"malformed CSV should fail, got {data}"
    assert data["error"], "a clear error message must be present"
    assert isinstance(data["error"], str) and data["error"].strip()


# --- Failure guard 2: question unanswerable from the columns (SQL mode) ---


def test_sql_unanswerable_question_no_fabricated_number(api_client):
    """Unanswerable question in SQL mode must not fabricate a number."""
    # There is no satisfaction column in sales.csv. The agent must NOT invent a
    # number — it either fails cleanly or returns a "no such column" answer.
    data = _post_sql(api_client, _csv_text("sales.csv"), "What is the average customer satisfaction score?")

    assert data["mode"] == "sql"

    if data["status"] == "failed":
        assert data["error"]
    else:
        # If it 'completed', it should say there is no such column.
        # It may return a result_table with a message or no result_table.
        text = (data["answer"] or "").lower() + " " + (data["explanation"] or "").lower()
        assert any(
            kw in text
            for kw in ("no column", "no such", "not a column", "does not", "doesn't", "cannot", "can't", "no satisfaction", "not available", "not present", "no data")
        ), f"expected a 'no such column' style answer, got {data}"


# --- Invariants (SQL mode) ---


def test_sql_show_its_work_invariant(api_client):
    """Every SUCCESSFUL SQL answer exposes non-empty generated code and a result."""
    data = _post_sql(api_client, _csv_text("sales.csv"), "What is the average of the sales column?")
    assert data["status"] == "completed", data.get("error")
    assert data["mode"] == "sql"
    assert data["generated_code"] and data["generated_code"].strip()
    assert "SELECT" in data["generated_code"].upper()
    # A result table OR a numeric answer must be present.
    assert data["result_table"] is not None or (data["answer"] and data["answer"].strip())


def test_sql_get_run_round_trip(api_client):
    """GET /runs/{id} retrieves a SQL mode run correctly."""
    # Create a SQL mode run via POST
    r = api_client.post(
        "/runs",
        json={"csv_text": _csv_text("sales.csv"), "question": "What were total sales by region, highest first?", "mode": "sql"}
    )
    assert r.status_code == 200
    created = r.json()["data"]
    run_id = created["run_id"]
    assert created["mode"] == "sql"

    # Fetch it back via GET
    r = api_client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    fetched = r.json()["data"]
    assert fetched["run_id"] == run_id
    assert fetched["status"] == created["status"]
    assert fetched["mode"] == created["mode"]
    assert fetched["answer"] == created["answer"]
    assert fetched["generated_code"] == created["generated_code"]
    assert fetched["result_table"] == created["result_table"]
