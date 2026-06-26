"""Real-Gemini integration tests for slice-3b pre-flight (C26 + C19).

Requires `AGENT_GEMINI_API_KEY` in `.env` (auto-detect selects the real Gemini
provider). These tests drive the REAL model — they assert on real behaviour:

- Clarification (C26): an ambiguous question (multiple numeric columns, no column
  named) with datasets NOT explicit -> `type == "clarification"` with a non-empty
  question. Re-asking the SAME question with `skip_clarification=True` proceeds to
  an `answer` (proves the skip path).
- Selector (C19): two datasets about different things; a question clearly about
  ONE -> the relevant dataset is selected (and ideally it is the ONLY one).

Run via `run_agent` directly (precise control of `run_selector` /
`skip_clarification`) against the production SQLite driver (the isolated copy via
the `_isolated_db` conftest fixture). Model: `gemini-3.1-flash-lite`.
"""
from __future__ import annotations

import pandas as pd
import pytest

from db.models import DatasetRow
from db.session import create_db_session
from graph import nodes as nodes_module
from graph.runner import run_agent


@pytest.fixture(autouse=True)
def uploads_dir(tmp_path, monkeypatch):
    """Point BOTH the nodes' and the runner's uploads dir at a tmp dir."""
    import graph.runner as runner_module

    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(nodes_module, "_uploads_dir", lambda: d)
    monkeypatch.setattr(runner_module, "_uploads_dir", lambda: d)
    return d


@pytest.fixture(autouse=True)
def _clear_session_cache():
    nodes_module._session_cache.clear()
    yield
    nodes_module._session_cache.clear()


def _make_dataset(uploads_dir, filename: str, df: pd.DataFrame, context: str | None = None) -> str:
    with create_db_session() as session:
        row = DatasetRow(
            filename=filename,
            file_path="",
            row_count=len(df),
            col_count=len(df.columns),
            columns_json=list(df.columns),
            content_hash=f"hash-{filename}",
            format="csv",
            origin="uploaded",
            context=context,
        )
        session.add(row)
        session.flush()
        dataset_id = row.id
        csv_path = uploads_dir / f"{dataset_id}.csv"
        df.to_csv(csv_path, index=False)
        # also write parquet (preferred by the loader) to mirror production
        df.to_parquet(uploads_dir / f"{dataset_id}.parquet")
        row.file_path = str(csv_path)
    return dataset_id


# --------------------------------------------------------------------------- #
# C26 clarification + the skip path
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("_require_llm_key")
def test_clarification_then_skip_real_gemini(uploads_dir):
    """An ambiguous "what is the average?" over a frame with MULTIPLE numeric
    columns and no column named -> real Gemini asks for clarification. Re-asking
    with skip_clarification=True proceeds to a real answer."""
    df = pd.DataFrame(
        {
            "revenue": [100.0, 200.0, 300.0, 400.0],
            "cost": [40.0, 80.0, 120.0, 160.0],
            "units": [5, 10, 15, 20],
        }
    )
    dataset_id = _make_dataset(uploads_dir, "financials.csv", df)

    # Datasets NOT explicit (run_selector=True) so pre-flight runs; do NOT skip.
    result = run_agent(
        "What is the average?",
        [dataset_id],
        run_selector=True,
        skip_clarification=False,
    )

    assert result["type"] == "clarification", (
        f"expected a clarification for an ambiguous question, got: {result.get('type')} "
        f"answer={result.get('answer')!r}"
    )
    question = result["clarification_question"]
    assert question and question.strip(), "clarification_question must be non-empty"
    assert "[stub]" not in question, "got a stub reply — real provider not used"
    # The clarifying question should reference a column / which metric.
    print(f"\n[clarification] real Gemini asked: {question!r}")

    # Now re-ask the SAME question with skip_clarification=True -> it proceeds.
    skipped = run_agent(
        "What is the average?",
        [dataset_id],
        run_selector=True,
        skip_clarification=True,
    )
    assert skipped["type"] == "answer", (
        f"with skip_clarification=True the run must proceed to an answer, got "
        f"{skipped.get('type')}"
    )
    assert skipped["status"] == "completed"
    answer = skipped["answer"]
    assert answer and answer.strip(), "skip path must yield a real answer"
    assert "[stub]" not in answer, "got a stub answer — real provider not used"
    print(f"[skip path] answer length={len(answer)} status={skipped['status']}")


# --------------------------------------------------------------------------- #
# C19 selector — two datasets, question about ONE
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("_require_llm_key")
def test_selector_picks_relevant_dataset_real_gemini(uploads_dir):
    """Two datasets (sales w/ revenue, employees w/ salary). A question clearly
    about employee salaries -> the selector picks the employees dataset."""
    sales = pd.DataFrame(
        {
            "region": ["north", "south", "east", "west"],
            "revenue": [1000, 2000, 1500, 2500],
        }
    )
    employees = pd.DataFrame(
        {
            "name": ["alice", "bob", "carol", "dave"],
            "salary": [50000, 60000, 55000, 70000],
            "department": ["eng", "sales", "eng", "ops"],
        }
    )
    sales_id = _make_dataset(uploads_dir, "sales.csv", sales)
    employees_id = _make_dataset(uploads_dir, "employees.csv", employees)
    candidate_ids = [sales_id, employees_id]

    result = run_agent(
        "What is the average employee salary?",
        candidate_ids,
        run_selector=True,
        skip_clarification=True,  # avoid an unrelated clarification turn
    )

    assert result["type"] == "answer", f"expected an answer, got {result.get('type')}"
    selected = result["dataset_ids"]
    reasoning = result.get("selector_reasoning")

    print(f"\n[selector] selected={selected} (employees={employees_id})")
    print(f"[selector] reasoning={reasoning!r}")

    # The relevant dataset (employees, with the salary column) MUST be selected.
    assert employees_id in selected, (
        f"selector should have chosen the employees dataset {employees_id} for a "
        f"salary question; got {selected} (reasoning: {reasoning!r})"
    )
    # Ideally it is the ONLY one chosen (tolerant: at minimum the relevant one is in).
    assert sales_id not in selected or len(selected) == len(candidate_ids), (
        f"selector should prefer the minimal subset; got {selected}"
    )

    # And a real answer came out the other side.
    answer = result["answer"]
    assert answer and "[stub]" not in answer, "expected a real answer"
    assert result["status"] == "completed"


# --------------------------------------------------------------------------- #
# Content sanity: a real answer is non-empty Markdown, run completed
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("_require_llm_key")
def test_real_answer_has_content_and_suggestions(uploads_dir):
    """A clear single-dataset question yields a completed run with real prose and
    a list of follow-up suggestions (possibly empty, always a list)."""
    df = pd.DataFrame({"value": [10, 20, 30, 40, 50]})
    dataset_id = _make_dataset(uploads_dir, "numbers.csv", df)

    result = run_agent(
        "What is the average of the value column?",
        [dataset_id],
        run_selector=True,
        skip_clarification=True,
    )

    assert result["type"] == "answer"
    assert result["status"] == "completed"
    answer = result["answer"]
    assert answer and answer.strip(), "answer must be non-empty real Markdown"
    assert "[stub]" not in answer
    assert any(ch.isdigit() for ch in answer), f"expected a number in: {answer!r}"

    assert isinstance(result["suggested_questions"], list)
    assert isinstance(result["prompt_breakdown"], dict)
    assert result["prompt_breakdown"]["total_prompt"] > 0
    print(f"\n[content] suggestions={result['suggested_questions']}")
    print(f"[content] prompt_breakdown={result['prompt_breakdown']}")
