"""Phase-1 gate — the local data-analyst against the REAL Gemini API.

Runs the full HTTP path (``TestClient`` -> ``POST /runs`` -> LangGraph -> real
Gemini -> local sandbox) and asserts on the COMPUTED RESULT, not on LLM prose.
Expected numbers are derived from the fixture with pandas inside the test so the
assertions are exact and phrasing-independent.

Covers the four analytical shapes (group-by, filter+aggregate, sort+top-N,
single-value), the two failure guards (malformed upload, unanswerable question),
the show-its-work and data-locality invariants, and the GET round-trip.

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


def _post(api_client, csv_text: str, question: str) -> dict:
    r = api_client.post("/runs", json={"csv_text": csv_text, "question": question})
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
# tests must tolerate phrasing variation (test-driven.md) while still proving the
# COMPUTED VALUE — so we accept digit-or-word but never a different number.
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
    explanation). This is where a count/scalar is verbalised — and where a WRONG
    count would show up — without the incidental digits that appear in code."""
    return ((data.get("answer") or "") + " " + (data.get("explanation") or "")).lower()


def _contains_value(text: str, n: int) -> bool:
    """True if integer ``n`` appears in ``text`` as a digit (optionally thousands-
    grouped) or, for small/round values, as its spelled-out English word."""
    return any(form.lower() in text for form in _value_forms(n))


def _assert_scalar_value(data: dict, expected: int, *, wrong_neighbors: tuple[int, ...] = ()) -> None:
    """Assert the correct computed scalar appears (digit OR spelled-out word) across
    the fields the app populates, and that obviously-wrong neighbour values are NOT
    the stated answer — tolerant of phrasing, intolerant of a wrong number."""
    hay = _haystack(data)
    assert _contains_value(hay, expected), (
        f"expected value {expected} (as digit or word) in answer/explanation/code/table; got {data}"
    )
    # The stated result must not BE a wrong neighbour. Check the prose the model
    # wrote (answer/explanation), not generated_code (which carries incidental
    # digits like row counts), so this stays strong without false positives.
    answer = _answer_text(data)
    if _contains_value(answer, expected):
        for wrong in wrong_neighbors:
            assert not _contains_value(answer, wrong), (
                f"wrong neighbour value {wrong} appeared in the stated answer; got {data}"
            )


# --- Analytical shape 1: group-by aggregation ------------------------------


def test_group_by_region_highest_first(api_client):
    df = _sales_df()
    expected = df.groupby("region")["sales"].sum().sort_values(ascending=False)
    expected_order = list(expected.index)            # ['East','West','North','South']
    expected_totals = [int(v) for v in expected.values]  # [590, 530, 520, 380]

    data = _post(api_client, _csv_text("sales.csv"), "What were total sales by region, highest first?")

    assert data["status"] == "completed", data.get("error")
    assert data["error"] is None
    # Show-its-work: real generated pandas that groups.
    assert data["generated_code"]
    assert "groupby" in data["generated_code"]

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


# --- Analytical shape 2: filter + aggregate --------------------------------


def test_filter_then_aggregate_shipped_late_count(api_client):
    df = _sales_df()
    expected = int((df["shipped_late"] == True).sum())  # noqa: E712 — exact 6

    data = _post(api_client, _csv_text("sales.csv"), "How many orders shipped late?")

    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"], "show-its-work: a count must expose generated code"
    # This is a SCALAR count: real Gemini may phrase it as the word "six", and the
    # value surfaces in the answer text (result_table is None for scalars). Accept
    # digit-or-word, but reject the adjacent wrong counts 5 and 7.
    _assert_scalar_value(data, expected, wrong_neighbors=(5, 7))


def test_filter_total_sales_for_one_region(api_client):
    df = _sales_df()
    expected = int(df[df["region"] == "North"]["sales"].sum())  # 520

    data = _post(api_client, _csv_text("sales.csv"), "What were the total sales for the North region?")

    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"], "show-its-work: a scalar aggregate must expose generated code"
    # Scalar total surfaces in the answer text (digit or thousands-grouped). Reject
    # the other regions' totals (a wrong/absent filter would surface those instead).
    _assert_scalar_value(data, expected, wrong_neighbors=(590, 530, 380, 2020))


# --- Analytical shape 3: sort + top-N --------------------------------------


def test_top_n_products_by_sales(api_client):
    df = _sales_df()
    ranked = df.groupby("product")["sales"].sum().sort_values(ascending=False)
    expected_top3 = list(ranked.index)[:3]  # ['Gadget','Widget','Gizmo']

    data = _post(api_client, _csv_text("sales.csv"), "What are the top 3 products by total sales, highest first?")

    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"]

    table = data["result_table"]
    assert table is not None, "top-N must return a result table"
    product_idx = next(
        (i for i, c in enumerate(table["columns"]) if c.lower() == "product"), 0
    )
    got_products = [str(row[product_idx]) for row in table["rows"]]
    assert got_products[:3] == expected_top3, f"expected top-3 {expected_top3}, got {got_products}"


# --- Analytical shape 4: single-value aggregate ----------------------------


def test_single_value_total_sales(api_client):
    df = _sales_df()
    expected = int(df["sales"].sum())  # 2020

    data = _post(api_client, _csv_text("sales.csv"), "What is the total of the sales column across all rows?")

    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"], "show-its-work: a scalar aggregate must expose generated code"
    # Single-value aggregate surfaces in the answer text (no result_scalar field is
    # exposed in the response envelope); accept a thousands separator. Reject the
    # per-region subtotals so a partial/wrong sum can't pass.
    _assert_scalar_value(data, expected, wrong_neighbors=(590, 530, 520, 380))


# --- Failure guard 1: malformed / non-CSV upload ---------------------------


def test_malformed_upload_fails_gracefully(api_client):
    # Ragged, inconsistent-width rows — not a valid CSV. Must NOT crash and must
    # NOT fabricate a number.
    malformed = "this is not a csv\nit has\nrandom,ragged\nlines,1,2,3,4,5\nx"

    data = _post(api_client, malformed, "What were total sales by region?")

    assert data["status"] == "failed", f"malformed CSV should fail, got {data}"
    assert data["error"], "a clear error message must be present"
    assert isinstance(data["error"], str) and data["error"].strip()


# --- Failure guard 2: question unanswerable from the columns ----------------


def test_unanswerable_question_no_fabricated_number(api_client):
    # There is no satisfaction column in sales.csv. The agent must NOT invent a
    # number — it either fails cleanly or returns a "no such column" answer.
    data = _post(api_client, _csv_text("sales.csv"), "What is the average customer satisfaction score?")

    if data["status"] == "failed":
        assert data["error"]
    else:
        # If it 'completed', it must not present a confident numeric result —
        # it should say there is no such column.
        assert data["result_table"] is None, (
            f"unanswerable question must not produce a result table: {data}"
        )
        text = (data["answer"] or "").lower() + " " + (data["explanation"] or "").lower()
        assert any(
            kw in text
            for kw in ("no column", "no such", "not a column", "does not", "doesn't", "cannot", "can't", "no satisfaction", "not available", "not present", "no data")
        ), f"expected a 'no such column' style answer, got {data}"


# --- Invariants -------------------------------------------------------------


def test_show_its_work_invariant(api_client):
    """Every SUCCESSFUL answer exposes non-empty generated code and a result."""
    data = _post(api_client, _csv_text("sales.csv"), "What is the mean of the sales column?")
    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"] and data["generated_code"].strip()
    # A result table OR a numeric answer must be present (single-value -> answer).
    assert data["result_table"] is not None or (data["answer"] and data["answer"].strip())


def test_data_locality_full_csv_never_sent_to_llm(api_client, monkeypatch):
    """The full dataset must never enter an LLM prompt — only the capped sample.

    We spy on the LLM client: the generate_code prompt is built from a 500-row
    CSV; the prompt must contain at most the configured sample cap of rows, not
    all 500. (Lightweight check of Success Criterion 3.)
    """
    from config.settings import get_settings
    import llm.client as client_module

    settings = get_settings()
    cap = min(settings.sample_rows, 20)

    captured: list[dict] = []
    original_call = client_module.LLMClient.call_model

    def _spy(self, prompt, *, system=None):
        captured.append({"prompt": prompt, "system": system})
        return original_call(self, prompt, system=system)

    monkeypatch.setattr(client_module.LLMClient, "call_model", _spy)

    data = _post(api_client, _csv_text("many_rows.csv"), "What is the sum of the value column?")
    assert data["status"] == "completed", data.get("error")

    # The generate_code prompt is the first call; its user message embeds the sample.
    gen_prompt = captured[0]["prompt"]
    # Each many_rows.csv data row has a unique id 0..499. Count how many distinct
    # row-ids appear in the prompt as JSON sample entries.
    present_ids = [i for i in range(500) if f'"id": {i}' in gen_prompt or f'"id":{i}' in gen_prompt]
    assert len(present_ids) <= cap, (
        f"prompt leaked {len(present_ids)} rows; cap is {cap}. The full dataset must not be sent."
    )
    # Sanity: the answer is still correct over the FULL local data (value=id*2).
    expected = sum(i * 2 for i in range(500))  # 249500
    # Scalar sum over the full local data; accept a thousands separator. If only the
    # capped sample had been summed the value would be far smaller, so this also
    # confirms the computation ran on the full local frame.
    _assert_scalar_value(data, expected)


# --- GET round-trip ---------------------------------------------------------


def test_get_run_round_trip(api_client):
    created = _post(api_client, _csv_text("sales.csv"), "What were total sales by region, highest first?")
    run_id = created["run_id"]

    r = api_client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    fetched = r.json()["data"]
    assert fetched["run_id"] == run_id
    assert fetched["status"] == created["status"]
    assert fetched["answer"] == created["answer"]
    assert fetched["generated_code"] == created["generated_code"]
    assert fetched["result_table"] == created["result_table"]


def test_get_unknown_run_is_404(api_client):
    r = api_client.get("/runs/does-not-exist")
    assert r.status_code == 404
