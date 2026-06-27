"""Graph nodes for the data analysis agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import text

from db.models import RunRow, AnalysisCacheRow, UploadedFileRow
from db.session import create_db_session
from graph.state import AnalysisState
from llm.client import LLMClient

log = structlog.get_logger(__name__)

_SQL_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_sql.md"
_INSIGHTS_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_insights.md"

_FORBIDDEN_KEYWORDS = frozenset(
    ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
)


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _strip_sql_fences(sql: str) -> str:
    """Remove ```sql ... ``` or ``` ... ``` fences."""
    sql = sql.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        # Remove first line (```sql or ```) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql


# ---------------------------------------------------------------------------
# Node: generate_sql
# ---------------------------------------------------------------------------

def generate_sql(state: AnalysisState) -> AnalysisState:
    """Build schema context from uploaded tables, call Gemini to generate SQL, validate."""
    log.info("generate_sql_start", run_id=state.get("run_id"))
    try:
        session_id = state["session_id"]
        question = state["question"]

        # Query uploaded files for this session
        with create_db_session() as db_session:
            rows = (
                db_session.query(UploadedFileRow)
                .filter(UploadedFileRow.session_id == session_id)
                .all()
            )
            uploaded_tables = [r.table_name for r in rows]

        if not uploaded_tables:
            return {**state, "error": "no_tables: No files uploaded for this session"}

        # Build schema context per table
        schema_parts = []
        with create_db_session() as db_session:
            engine = db_session.get_bind()
            for table_name in uploaded_tables:
                # Get column info
                col_info = db_session.execute(
                    text(f"PRAGMA table_info({table_name})")
                ).fetchall()
                cols = [{"name": row[1], "type": row[2]} for row in col_info]

                # Get 20 sample rows
                try:
                    sample_result = db_session.execute(
                        text(f"SELECT * FROM {table_name} LIMIT 20")
                    )
                    col_names = list(sample_result.keys())
                    sample_rows = [dict(zip(col_names, r)) for r in sample_result.fetchall()]
                except Exception:
                    sample_rows = []

                schema_parts.append(
                    f"Table: {table_name}\n"
                    f"Columns: {json.dumps(cols)}\n"
                    f"Sample rows (up to 20):\n{json.dumps(sample_rows, default=str)}"
                )

        schema_context = "\n\n---\n\n".join(schema_parts)

        # Call LLM for SQL
        prompt_template = _load_prompt(_SQL_PROMPT_PATH)
        user_message = f"Schema:\n{schema_context}\n\nQuestion: {question}"
        sql_raw = LLMClient().call_model(user_message, system=prompt_template)

        # Strip fences
        sql_query = _strip_sql_fences(sql_raw)

        # Enforce SELECT-only restriction
        sql_upper = sql_query.upper()
        for kw in _FORBIDDEN_KEYWORDS:
            if kw in sql_upper:
                return {**state, "error": f"forbidden_sql_operation: SQL contains forbidden keyword {kw}"}

        # Validate with EXPLAIN QUERY PLAN
        with create_db_session() as db_session:
            try:
                db_session.execute(text(f"EXPLAIN QUERY PLAN {sql_query}"))
            except Exception as exc:
                return {**state, "error": f"invalid_sql: {exc}"}

        log.info("generate_sql_done", run_id=state.get("run_id"), sql=sql_query[:120])
        return {
            **state,
            "uploaded_tables": uploaded_tables,
            "schema_context": schema_context,
            "sql_query": sql_query,
        }

    except Exception as exc:
        log.error("generate_sql_error", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": str(exc)}


# ---------------------------------------------------------------------------
# Node: execute_sql
# ---------------------------------------------------------------------------

def execute_sql(state: AnalysisState) -> AnalysisState:
    """Execute the validated SQL query and return rows (capped at 10,000)."""
    log.info("execute_sql_start", run_id=state.get("run_id"))
    try:
        sql_query = state["sql_query"]

        with create_db_session() as db_session:
            # Strip trailing semicolon before wrapping (subqueries cannot end with ;)
            sql_stripped = sql_query.rstrip().rstrip(";").rstrip()
            wrapped_sql = f"SELECT * FROM ({sql_stripped}) LIMIT 10000"
            result = db_session.execute(text(wrapped_sql))
            col_names = list(result.keys())
            raw_rows = result.fetchall()
            query_rows = [dict(zip(col_names, row)) for row in raw_rows]

        rows_truncated = len(query_rows) == 10000

        log.info(
            "execute_sql_done",
            run_id=state.get("run_id"),
            row_count=len(query_rows),
            truncated=rows_truncated,
        )
        return {**state, "query_rows": query_rows, "rows_truncated": rows_truncated}

    except Exception as exc:
        log.error("execute_sql_error", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"execution_error: {exc}"}


# ---------------------------------------------------------------------------
# Node: generate_insights
# ---------------------------------------------------------------------------

def generate_insights(state: AnalysisState) -> AnalysisState:
    """Compute statistics from query_rows, call Gemini for prose narrative."""
    log.info("generate_insights_start", run_id=state.get("run_id"))
    try:
        query_rows = state.get("query_rows", [])
        question = state.get("question", "")

        if not query_rows:
            insight_json: dict[str, Any] = {
                "row_count": 0,
                "numeric_columns": {},
                "top3": {},
                "bottom3": {},
                "anomalies": [],
                "trends": [],
                "truncated": False,
            }
            insight_text = "The query returned no results."
            return {
                **state,
                "insight_json": insight_json,
                "insight_text": insight_text,
                "output_text": insight_text,
            }

        df = pd.DataFrame(query_rows)

        # Identify numeric and date columns
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        date_cols = []
        for col in df.columns:
            if col not in numeric_cols:
                try:
                    converted = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                    if converted.notna().sum() > len(df) * 0.5:
                        date_cols.append(col)
                except Exception:
                    pass

        # Compute numeric column stats
        numeric_stats: dict[str, Any] = {}
        for col in numeric_cols:
            series = df[col].dropna()
            if series.empty:
                continue
            numeric_stats[col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "median": float(series.median()),
                "count": int(series.count()),
                "null_count": int(df[col].isna().sum()),
            }

        # Top3 / bottom3 per numeric column
        top3: dict[str, list] = {}
        bottom3: dict[str, list] = {}
        for col in numeric_cols:
            series = df[col].dropna().sort_values(ascending=False)
            top3[col] = [float(v) for v in series.head(3).tolist()]
            bottom3[col] = [float(v) for v in series.tail(3).tolist()]

        # Anomaly detection: rows where |value - mean| > 3 * std
        anomalies: list[dict[str, Any]] = []
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue
            mean = series.mean()
            std = series.std()
            if std == 0:
                continue
            outlier_mask = (df[col] - mean).abs() > 3 * std
            outlier_rows = df[outlier_mask]
            for _, row in outlier_rows.iterrows():
                anomalies.append({
                    "column": col,
                    "value": float(row[col]),
                    "mean": float(mean),
                    "std": float(std),
                    "z_score": float(abs(row[col] - mean) / std),
                })

        # Trends: if date column exists, compute first/last difference for numeric cols
        trends: list[dict[str, Any]] = []
        if date_cols and numeric_cols:
            date_col = date_cols[0]
            try:
                df_sorted = df.copy()
                df_sorted[date_col] = pd.to_datetime(df_sorted[date_col], errors="coerce")
                df_sorted = df_sorted.dropna(subset=[date_col]).sort_values(date_col)
                for num_col in numeric_cols[:3]:  # limit to first 3 numeric cols
                    if df_sorted[num_col].notna().sum() >= 2:
                        first_val = float(df_sorted[num_col].dropna().iloc[0])
                        last_val = float(df_sorted[num_col].dropna().iloc[-1])
                        trends.append({
                            "column": num_col,
                            "first_value": first_val,
                            "last_value": last_val,
                            "change": last_val - first_val,
                        })
            except Exception:
                pass

        insight_json = {
            "row_count": len(df),
            "numeric_columns": numeric_stats,
            "top3": top3,
            "bottom3": bottom3,
            "anomalies": anomalies,
            "trends": trends,
            "truncated": state.get("rows_truncated", False),
        }

        # Call LLM for prose narrative
        prompt_template = _load_prompt(_INSIGHTS_PROMPT_PATH)
        user_message = (
            f"Question: {question}\n\nStatistics:\n{json.dumps(insight_json, default=str)}"
        )
        raw_insight = LLMClient().call_model(user_message, system=prompt_template).strip()
        # Enforce 600-char cap (spec requirement); truncate at sentence boundary when possible
        _MAX_INSIGHT_LEN = 600
        if len(raw_insight) > _MAX_INSIGHT_LEN:
            # Find last sentence-ending punctuation within cap
            candidate = raw_insight[:_MAX_INSIGHT_LEN]
            for sep in (".", "!", "?"):
                last = candidate.rfind(sep)
                if last > _MAX_INSIGHT_LEN // 2:
                    candidate = candidate[: last + 1]
                    break
            else:
                # Fallback: truncate at last space
                last_space = candidate.rfind(" ")
                if last_space > _MAX_INSIGHT_LEN // 2:
                    candidate = candidate[:last_space]
            insight_text = candidate
        else:
            insight_text = raw_insight

        log.info("generate_insights_done", run_id=state.get("run_id"), text_len=len(insight_text))
        return {
            **state,
            "insight_json": insight_json,
            "insight_text": insight_text,
            "output_text": insight_text,
        }

    except Exception as exc:
        log.error("generate_insights_error", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": str(exc)}


# ---------------------------------------------------------------------------
# Node: generate_charts
# ---------------------------------------------------------------------------

def generate_charts(state: AnalysisState) -> AnalysisState:
    """Auto-select up to 4 chart types from column dtypes. Degrades to [] on any error."""
    log.info("generate_charts_start", run_id=state.get("run_id"))
    try:
        query_rows = state.get("query_rows", [])
        if not query_rows:
            return {**state, "chart_specs": [], "error": None}

        df = pd.DataFrame(query_rows)
        chart_specs: list[dict[str, Any]] = []

        # Identify column types
        numeric_cols = df.select_dtypes(include="number").columns.tolist()

        # Detect date columns
        date_cols = []
        for col in df.columns:
            if col in numeric_cols:
                continue
            try:
                converted = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                if converted.notna().sum() > len(df) * 0.5:
                    date_cols.append(col)
            except Exception:
                pass

        # Detect categorical columns (2-30 distinct string values)
        cat_cols = []
        for col in df.columns:
            if col in numeric_cols or col in date_cols:
                continue
            n_unique = df[col].nunique()
            if 2 <= n_unique <= 30:
                cat_cols.append(col)

        def _sample_data(data: list[dict], max_pts: int = 500) -> tuple[list[dict], bool]:
            if len(data) <= max_pts:
                return data, False
            step = len(data) // max_pts
            sampled = data[::step][:max_pts]
            return sampled, True

        # Priority 1: Line chart — date + numeric
        if date_cols and numeric_cols:
            date_col = date_cols[0]
            y_col = numeric_cols[0]
            data = df[[date_col, y_col]].dropna().to_dict(orient="records")
            # Convert date to string for JSON serialization
            data = [{**r, date_col: str(r[date_col])} for r in data]
            sampled_data, was_sampled = _sample_data(data)
            chart_specs.append({
                "chart_type": "line",
                "title": f"{y_col} over time",
                "x_key": date_col,
                "y_key": y_col,
                "data": sampled_data,
                "sampled": was_sampled,
            })

        # Priority 2: Bar chart — categorical + numeric
        if cat_cols and numeric_cols:
            x_col = cat_cols[0]
            y_col = numeric_cols[0]
            # Aggregate: mean per category
            agg = df.groupby(x_col)[y_col].mean().reset_index()
            data = agg.to_dict(orient="records")
            sampled_data, was_sampled = _sample_data(data)
            chart_specs.append({
                "chart_type": "bar",
                "title": f"{y_col} by {x_col}",
                "x_key": x_col,
                "y_key": y_col,
                "data": sampled_data,
                "sampled": was_sampled,
            })

        # Priority 3: Histogram — single numeric column (if no other charts selected yet for histograms)
        if numeric_cols and len(chart_specs) < 4:
            num_col = numeric_cols[0] if not date_cols else (numeric_cols[1] if len(numeric_cols) > 1 else None)
            if num_col is None and not date_cols:
                num_col = numeric_cols[0]
            if num_col and len(numeric_cols) == 1:
                # Only add histogram if we have exactly 1 numeric col (no bar/line would have been added)
                if not cat_cols and not date_cols:
                    series = df[num_col].dropna()
                    # Build histogram bins
                    try:
                        counts, bin_edges = pd.cut(series, bins=20, retbins=True)
                        hist_data = []
                        for i in range(len(bin_edges) - 1):
                            bin_label = f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}"
                            count = int((counts == counts.cat.categories[i]).sum())
                            hist_data.append({"bin": bin_label, "count": count})
                        chart_specs.append({
                            "chart_type": "histogram",
                            "title": f"Distribution of {num_col}",
                            "x_key": "bin",
                            "y_key": "count",
                            "data": hist_data,
                            "sampled": False,
                        })
                    except Exception:
                        pass

        # Priority 4: Scatter — two+ numeric columns
        if len(numeric_cols) >= 2 and len(chart_specs) < 4:
            x_col = numeric_cols[0]
            y_col = numeric_cols[1]
            data = df[[x_col, y_col]].dropna().to_dict(orient="records")
            sampled_data, was_sampled = _sample_data(data)
            chart_specs.append({
                "chart_type": "scatter",
                "title": f"{y_col} vs {x_col}",
                "x_key": x_col,
                "y_key": y_col,
                "data": sampled_data,
                "sampled": was_sampled,
            })

        # Limit to 4 chart specs
        chart_specs = chart_specs[:4]

        log.info("generate_charts_done", run_id=state.get("run_id"), chart_count=len(chart_specs))
        return {**state, "chart_specs": chart_specs, "error": state.get("error")}

    except Exception as exc:
        log.warning("generate_charts_error_degraded", run_id=state.get("run_id"), error=str(exc))
        # Charts are non-critical; set chart_specs=[] and clear any error we set here
        return {**state, "chart_specs": [], "error": None}


# ---------------------------------------------------------------------------
# Node: handle_error
# ---------------------------------------------------------------------------

def handle_error(state: AnalysisState) -> AnalysisState:
    """Log error and update RunRow to failed status."""
    error = state.get("error", "unknown error")
    run_id = state.get("run_id")
    log.error("handle_error", run_id=run_id, error=error)

    try:
        with create_db_session() as db_session:
            run = db_session.get(RunRow, run_id)
            if run:
                run.status = "failed"
                run.error_message = error
    except Exception as exc:
        log.error("handle_error_db_update_failed", run_id=run_id, error=str(exc))

    return state


# ---------------------------------------------------------------------------
# Node: finalize
# ---------------------------------------------------------------------------

def finalize(state: AnalysisState) -> AnalysisState:
    """Write all result fields to RunRow and cache in analysis_cache."""
    import hashlib

    run_id = state.get("run_id")
    log.info("finalize_start", run_id=run_id)

    try:
        question = state.get("question", "")
        sql_query = state.get("sql_query", "")
        insight_json = state.get("insight_json", {})
        insight_text = state.get("insight_text", "")
        output_text = state.get("output_text", insight_text)
        chart_specs = state.get("chart_specs", [])
        uploaded_tables = state.get("uploaded_tables", [])

        with create_db_session() as db_session:
            run = db_session.get(RunRow, run_id)
            if run:
                run.status = "completed"
                run.question = question
                run.sql_query = sql_query
                run.insight_json = json.dumps(insight_json, default=str)
                run.chart_specs = json.dumps(chart_specs, default=str)
                run.output_text = output_text

        # Compute hashes for cache
        question_hash = hashlib.sha256(question.strip().lower().encode()).hexdigest()

        # Table hash: SHA-256 of sorted "table_name:row_count" pairs
        with create_db_session() as db_session:
            file_rows = (
                db_session.query(UploadedFileRow)
                .filter(UploadedFileRow.session_id == state.get("session_id", ""))
                .order_by(UploadedFileRow.table_name)
                .all()
            )
            table_pairs = sorted(f"{r.table_name}:{r.row_count}" for r in file_rows)
        table_hash = hashlib.sha256("|".join(table_pairs).encode()).hexdigest()

        # Write to analysis_cache (INSERT OR IGNORE semantics — skip on duplicate)
        result_json = json.dumps({
            "sql_query": sql_query,
            "insight_json": insight_json,
            "chart_specs": chart_specs,
            "output_text": output_text,
        }, default=str)

        try:
            with create_db_session() as db_session:
                existing = (
                    db_session.query(AnalysisCacheRow)
                    .filter(
                        AnalysisCacheRow.question_hash == question_hash,
                        AnalysisCacheRow.table_hash == table_hash,
                    )
                    .first()
                )
                if not existing:
                    cache_row = AnalysisCacheRow(
                        question_hash=question_hash,
                        table_hash=table_hash,
                        result_json=result_json,
                    )
                    db_session.add(cache_row)
        except Exception as exc:
            log.warning("finalize_cache_write_failed", run_id=run_id, error=str(exc))

        log.info("finalize_done", run_id=run_id)

    except Exception as exc:
        log.error("finalize_error", run_id=run_id, error=str(exc))

    return state
