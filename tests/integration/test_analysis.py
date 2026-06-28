"""Integration tests for the DataChat analysis agent — REAL Gemini via .env.

The data-correctness gate: a question is answered by the full plan-execute loop
(plan -> generate_code -> execute_local -> synthesize) against the LARGE fixture
where a 20-row sample and the full file give DIFFERENT aggregates. The persisted
MessageRow must be ``completed`` with a plan, code, answer, key numbers, tokens,
and a non-zero cost — AND the computed numbers must match a DIRECT pandas
computation on the FULL file (proving the answer reflects the full data, not the
sample the LLM saw).

A second test exercises the failure path: a question whose generated code is
likely to break must, after the single self-correction retry, either succeed or
persist a ``failed`` MessageRow carrying the real error + the offending code
(transparency).

These call the real API; they ``pytest.skip`` only if the Gemini key is genuinely
absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from db import session as session_module
from db.models import DatasetRow, MessageRow
from execution.profile import load_csv, profile_dataframe
from graph.runner import run_analysis

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LARGE_CSV = FIXTURES / "large_sales.csv"


@pytest.fixture
def _require_gemini_key():
    """Skip only if no Gemini key is set (the data agent uses Gemini)."""
    from config.settings import get_settings

    s = get_settings()
    if not s.gemini_api_key and not (s.llm_provider == "gemini" and s.anthropic_api_key):
        if not s.gemini_api_key:
            pytest.skip("No Gemini key in .env (AGENT_GEMINI_API_KEY)")


@pytest.fixture
def large_dataset(_isolated_db, tmp_path):
    """Seed a datasets row pointing at the LARGE fixture and return its id.

    The file_path is the real on-disk fixture so the sandbox loads the FULL
    60k-row file; the profile_json carries only the bounded sample (what the LLM
    is allowed to see).
    """
    assert LARGE_CSV.exists(), f"missing fixture {LARGE_CSV}"
    df = load_csv(str(LARGE_CSV))
    profile = profile_dataframe(df, sample_rows=20)

    with Session(session_module._engine) as s:
        row = DatasetRow(
            name="large_sales.csv",
            original_filename="large_sales.csv",
            file_path=str(LARGE_CSV),
            profile_json=json.dumps(profile),
            source_kind="csv",
        )
        s.add(row)
        s.commit()
        dataset_id = row.id
    return dataset_id


@pytest.mark.usefixtures("_require_gemini_key")
def test_groupby_answer_matches_full_file_not_sample(large_dataset):
    """The data-correctness gate.

    Ask for mean revenue by region. The sample (first 20 rows) sees only
    "North" with a mean near 3; the FULL file has 5 regions with means near
    1000. The persisted answer's key numbers MUST match the full-file means.
    """
    # Ground truth from the full file, computed directly.
    df = load_csv(str(LARGE_CSV))
    full_truth = df.groupby("region")["revenue"].mean()
    sample_truth = df.head(20).groupby("region")["revenue"].mean()
    # Sanity: the sample really is misleading (one region, tiny value).
    assert df.head(20)["region"].nunique() == 1
    assert abs(full_truth["North"] - sample_truth["North"]) > 100

    message_id = run_analysis(large_dataset, "What is the average revenue for each region?")

    with Session(session_module._engine) as s:
        msg = s.get(MessageRow, message_id)

    assert msg is not None
    assert msg.status == "completed", f"run failed: {msg.error}\ncode:\n{msg.generated_code}"
    assert msg.plan and len(msg.plan) > 5
    assert msg.generated_code and "result" in msg.generated_code
    assert msg.answer and len(msg.answer) > 20
    assert msg.prompt_tokens > 0
    assert msg.completion_tokens > 0
    assert msg.cost_usd > 0.0
    assert msg.completed_at is not None
    assert msg.error is None

    # The computed key numbers must reflect the FULL file's per-region means.
    key_numbers = json.loads(msg.key_numbers_json) if msg.key_numbers_json else {}
    result_table = json.loads(msg.result_table_json) if msg.result_table_json else None
    assert key_numbers or result_table, "no computed result persisted"

    # Pull each region's computed mean out of whichever shape the code produced
    # (a Series -> key_numbers keyed by region; a DataFrame -> result_table rows).
    computed = _extract_region_means(key_numbers, result_table)
    assert computed, f"could not locate per-region means in result: {key_numbers} / {result_table}"

    # Every region present must match the FULL-file mean (NOT the sample's value).
    for region, full_mean in full_truth.items():
        if region in computed:
            assert computed[region] == pytest.approx(full_mean, rel=1e-3), (
                f"{region}: computed {computed[region]} != full-file {full_mean}"
            )
    # And at least the dominant region must be present and full-file-correct.
    assert "North" in computed
    assert computed["North"] == pytest.approx(full_truth["North"], rel=1e-3)
    # Emphatically NOT the misleading 20-row sample value.
    assert computed["North"] != pytest.approx(sample_truth["North"], rel=1e-2)


def _extract_region_means(key_numbers: dict, result_table) -> dict[str, float]:
    """Locate region -> mean from the persisted result, tolerant of shape.

    The model may produce a Series (key_numbers keyed by region) or a DataFrame
    (result_table of {region, revenue}-ish rows). Return a flat region->float
    mapping for whichever it produced.
    """
    out: dict[str, float] = {}
    region_names = {"North", "South", "East", "West", "Central"}

    # Series shape: key_numbers is region -> value.
    if key_numbers:
        if region_names & set(key_numbers.keys()):
            for k, v in key_numbers.items():
                if k in region_names and isinstance(v, (int, float)):
                    out[k] = float(v)
            if out:
                return out

    # DataFrame shape: result_table rows with a region column and a numeric value.
    if result_table and isinstance(result_table, list):
        for row in result_table:
            if not isinstance(row, dict):
                continue
            region = None
            value = None
            for k, v in row.items():
                if isinstance(v, str) and v in region_names:
                    region = v
                elif isinstance(v, str) and k.lower() in {"region", "key"} and v in region_names:
                    region = v
                elif isinstance(v, (int, float)):
                    value = float(v)
            # Series-normalized table is [{"key": region, "value": mean}].
            if region is None and "key" in row and row["key"] in region_names:
                region = row["key"]
                value = float(row["value"]) if isinstance(row.get("value"), (int, float)) else value
            if region is not None and value is not None:
                out[region] = value

    return out


@pytest.mark.usefixtures("_require_gemini_key")
def test_failure_path_persists_error_and_code_transparently(large_dataset):
    """A question referencing a column that does not exist.

    After at most one self-correction retry, the run either succeeds (the model
    adapted) or is persisted as ``failed`` carrying the REAL error + the
    offending code — never a silent swallow, never a 500.
    """
    message_id = run_analysis(
        large_dataset,
        "What is the total of the 'nonexistent_column_xyz' field?",
    )

    with Session(session_module._engine) as s:
        msg = s.get(MessageRow, message_id)

    assert msg is not None
    assert msg.status in {"completed", "failed"}
    assert msg.completed_at is not None
    if msg.status == "failed":
        # Transparency: the real error and the code that caused it are persisted.
        assert msg.error and len(msg.error) > 0
        assert msg.generated_code, "offending code must be persisted on failure"
    else:
        # If the model adapted (e.g. realized the column is absent and answered
        # gracefully), that is acceptable — but it still produced a real run.
        assert msg.answer
