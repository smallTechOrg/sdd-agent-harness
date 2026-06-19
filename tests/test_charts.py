"""visualize-data capability — create_chart (read-only SQL + Vega-Lite).

Offline: refusal of writes, bad-JSON handling, and a mechanical chart build (no LLM). Real (key-gated):
a chart-requesting run produces a data-backed Vega-Lite spec and the create_chart tool fires.
"""
import os
import tempfile

import pytest

import agent.duck as duck
from agent.config import get_settings
from agent.evals import trajectory_eval
from agent.runner import run_agent
from agent.seed import seed
from agent.tools import create_chart, current_dataset, run_charts

HAS_KEY = bool(get_settings().llm_api_key)
GOOD_SPEC = '{"mark":"bar","encoding":{"x":{"field":"cat"},"y":{"field":"total"}}}'


def test_create_chart_refuses_write():
    out = create_chart.invoke({"title": "x", "sql": "DROP TABLE t", "vega_lite_spec_json": GOOD_SPEC})
    assert out.startswith("REFUSED")


def test_create_chart_rejects_bad_json():
    out = create_chart.invoke({"title": "x", "sql": "SELECT 1 AS a", "vega_lite_spec_json": "{not json"})
    assert "invalid Vega-Lite JSON" in out


def test_create_chart_rejects_spec_without_mark_encoding():
    out = create_chart.invoke({"title": "x", "sql": "SELECT 1 AS a", "vega_lite_spec_json": '{"foo":1}'})
    assert "must be a JSON object with at least 'mark' and 'encoding'" in out


def test_create_chart_builds_data_backed_spec():
    """Mechanical (no LLM): the tool runs the SQL and embeds the rows as Vega-Lite data.values."""
    ds = "chart_test_ds"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w")
    tmp.write("cat,amt\nA,10\nB,20\nA,5\n")
    tmp.close()
    try:
        duck.ingest_file(ds, "t", tmp.name, "t.csv")
    finally:
        os.unlink(tmp.name)

    tok_d = current_dataset.set(ds)
    tok_c = run_charts.set([])
    try:
        out = create_chart.invoke({
            "title": "By cat", "vega_lite_spec_json": GOOD_SPEC,
            "sql": "SELECT cat, sum(amt) AS total FROM t GROUP BY cat ORDER BY total DESC",
        })
        assert "created" in out
        charts = run_charts.get()
        assert len(charts) == 1
        spec = charts[0]["spec"]
        assert spec["mark"] == "bar"
        values = spec["data"]["values"]
        assert {row["cat"] for row in values} == {"A", "B"}        # real rows embedded
        assert any(row["total"] == 20 for row in values)
    finally:
        current_dataset.reset(tok_d)
        run_charts.reset(tok_c)


@pytest.mark.skipif(not HAS_KEY, reason="no funded APP_LLM_API_KEY (real-run)")
async def test_chart_request_produces_chart():
    dataset_id = await seed()
    r = await run_agent("Show a bar chart of total sales by category", dataset_id=dataset_id)
    assert r["status"] == "completed"
    assert len(r["charts"]) >= 1, "expected at least one chart"
    spec = r["charts"][0]["spec"]
    assert "mark" in spec and "encoding" in spec and spec["data"]["values"], "chart must be data-backed"
    ok_t, reasons = await trajectory_eval(r["run_id"], expect_tools=["create_chart"])
    assert ok_t, f"create_chart should have fired: {reasons}"
