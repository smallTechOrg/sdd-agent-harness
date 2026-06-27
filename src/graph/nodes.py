import json
import re
from pathlib import Path

import pandas as pd

from graph.state import AgentState
from llm.client import LLMClient
from db.session import create_db_session
from db.models import DatasetRow

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analyze.md"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def analyze_data(state: AgentState) -> AgentState:
    try:
        dataset_id = state.get("dataset_id")
        question = state.get("question")
        if not dataset_id or not question:
            return {**state, "error": "dataset_id and question are required"}

        # Load dataset metadata from DB
        with create_db_session() as session:
            dataset = session.get(DatasetRow, dataset_id)
            if not dataset:
                return {**state, "error": f"Dataset {dataset_id} not found"}
            file_path = dataset.file_path
            columns_json = dataset.columns_json
            sample_rows_json = dataset.sample_rows_json

        # Load full DataFrame (stays local — never sent to Gemini)
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Build schema text for prompt
        columns = json.loads(columns_json)
        schema_text = "| Column | Type |\n|--------|------|\n"
        schema_text += "\n".join(f"| {c['name']} | {c['dtype']} |" for c in columns)

        # Build sample CSV text for prompt (20 rows max — NEVER full data)
        sample_rows = json.loads(sample_rows_json)
        sample_df = pd.DataFrame(sample_rows[:20])
        sample_csv = sample_df.to_csv(index=False)

        # Build prompt from template
        prompt_template = _load_prompt()
        prompt = prompt_template.replace("{schema_text}", schema_text)
        prompt = prompt.replace("{sample_csv}", sample_csv)
        prompt = prompt.replace("{question}", question)

        # Call Gemini (schema + 20 rows only — NEVER the full DataFrame)
        raw = LLMClient().call_model(prompt)

        # Parse JSON response — strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        gemini_result = json.loads(raw)

        pandas_code = gemini_result.get("pandas_code", "")
        chart_type = gemini_result.get("chart_type", "bar")
        summary = gemini_result.get("summary", "")

        # Execute pandas code LOCALLY against the FULL DataFrame
        # Gemini's illustrative labels/values are replaced by real results
        namespace = {"df": df.copy(), "pd": pd}
        exec(pandas_code, namespace)  # noqa: S102
        result = namespace.get("result")

        if not isinstance(result, dict) or "labels" not in result or "values" not in result:
            return {**state, "error": "pandas_code did not produce expected result dict with labels and values"}

        labels = [str(x) for x in result["labels"]]
        values = [float(x) for x in result["values"]]

        if len(labels) != len(values) or len(labels) == 0:
            return {**state, "error": "labels and values must be non-empty arrays of equal length"}

        return {**state, "chart_type": chart_type, "labels": labels, "values": values, "summary": summary}

    except json.JSONDecodeError as e:
        return {**state, "error": f"Failed to parse Gemini JSON response: {e}"}
    except Exception as e:
        return {**state, "error": f"Analysis failed: {e}"}


def handle_error(state: AgentState) -> AgentState:
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}
