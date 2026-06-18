import json
import sqlite3

import pandas as pd
import structlog

from data_analysis_agent.graph.state import AgentState

log = structlog.get_logger()

_db_cache: dict[str, sqlite3.Connection] = {}


def _cleanup_db(run_id: str) -> None:
    conn = _db_cache.pop(run_id, None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass


def _load_tool_registry(session_id: str) -> tuple[list[dict], list[dict]]:
    """Returns (tools_list, data_sources_list) for all data sources in the session."""
    from data_analysis_agent.db.session import create_db_session
    from data_analysis_agent.db.models import DataSourceRow, SessionDataSourceRow, ToolRow, ToolCapabilityRow
    with create_db_session() as db:
        links = (
            db.query(SessionDataSourceRow)
            .filter(SessionDataSourceRow.session_id == session_id)
            .all()
        )
        data_source_ids = [lnk.data_source_id for lnk in links]

        tools_result = []
        sources_result = []
        for ds_id in data_source_ids:
            ds = db.get(DataSourceRow, ds_id)
            if ds:
                sources_result.append({
                    "id": ds.id,
                    "name": ds.name,
                    "type": ds.type,
                    "file_path": ds.file_path,
                    "column_names": ds.column_names,
                    "row_count": ds.row_count,
                })
            tools = db.query(ToolRow).filter(ToolRow.data_source_id == ds_id).all()
            for tool in tools:
                caps = db.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == tool.id).all()
                tools_result.append({
                    "name": tool.name,
                    "type": tool.type,
                    "description": tool.description,
                    "config": tool.config,
                    "data_source_id": tool.data_source_id,
                    "capabilities": [
                        {
                            "name": c.name,
                            "description": c.description,
                            "parameter_schema": c.parameter_schema,
                        }
                        for c in caps
                    ],
                })
        return tools_result, sources_result


def _build_plan_prompt(state: AgentState) -> str:
    tools: list[dict] = state.get("tools", [])
    question = state["question"]
    history: list[dict] = state.get("action_history", [])

    lines = ["<node:plan_action>"]

    # Tool descriptions
    if tools:
        lines.append("Available tools:")
        lines.append("")
        for tool in tools:
            lines.append(f"Tool: {tool['name']}")
            for cap in tool.get("capabilities", []):
                lines.append(f"  Capability: {cap['name']}")
                lines.append(f"  Description: {cap['description']}")
                params = cap.get("parameter_schema", {})
                lines.append(f"  Parameters: {json.dumps(params)}")
            lines.append("")

    # Build schema section grouped by actual table name
    from collections import defaultdict
    table_cols: dict[str, list[str]] = defaultdict(list)
    for col in state.get("column_names", []):
        if "." in col:
            tbl, colname = col.split(".", 1)
            table_cols[tbl].append(colname)
        else:
            table_cols["data"].append(col)

    lines.append("Dataset schema:")
    for tbl, cols in table_cols.items():
        lines.append(f"  Table: {tbl} — Columns: {', '.join(cols)}")
    lines.append("")

    lines.extend([
        f"User question: {question}",
    ])

    if history:
        lines.append("")
        lines.append("Previous tool calls and results:")
        for i, entry in enumerate(history, 1):
            lines.append(f'[{i}] capability: {entry["capability"]}')
            lines.append(f'    parameters: {json.dumps(entry["parameters"])}')
            if entry.get("is_error"):
                lines.append(f'    result: Error: {entry["result"]}')
                lines.append("    → This call failed. Please write a corrected query.")
            else:
                lines.append(f'    result:\n{entry["result"]}')

    lines.extend([
        "",
        "Decide your next step:",
        "- If you need more data: respond with a JSON tool call (no markdown, no backticks):",
        '  {"capability": "run_query", "parameters": {"query": "SELECT ..."}}',
        "- If you have enough information to answer: respond with exactly:",
        "  FINAL ANSWER: <your complete answer here>",
    ])

    return "\n".join(lines)


def _table_name_for(source_name: str) -> str:
    """Derive a SQL-safe table name from a data source name."""
    import re
    name = re.sub(r'[^\w]', '_', source_name.rsplit('.', 1)[0]).lower()
    name = re.sub(r'_+', '_', name).strip('_') or 'data'
    if name[0].isdigit():
        name = 'ds_' + name
    return name


def load_data(state: AgentState) -> AgentState:
    try:
        tools, data_sources = _load_tool_registry(state["session_id"])

        if not data_sources:
            return {**state, "error": "No data sources attached to this session"}

        conn = sqlite3.connect(":memory:")
        _db_cache[state["run_id"]] = conn

        all_column_names: list[str] = []
        total_rows = 0

        # Load each CSV into the shared in-memory SQLite under its own table name
        updated_tools = []
        for ds in data_sources:
            if ds["type"] == "csv" and ds.get("file_path"):
                table = _table_name_for(ds["name"])
                df = pd.read_csv(ds["file_path"])
                df.to_sql(table, conn, index=False, if_exists="replace")
                all_column_names.extend([f"{table}.{c}" for c in df.columns])
                total_rows += len(df)

        # Ensure each tool's config has the correct runtime table name
        for tool in tools:
            if tool["type"] == "csv_query":
                ds_id = tool.get("data_source_id")
                matching_ds = next((d for d in data_sources if d["id"] == ds_id), None)
                if matching_ds:
                    table = _table_name_for(matching_ds["name"])
                    tool = dict(tool)
                    tool["config"] = {**tool.get("config", {}), "table_name": table}
            updated_tools.append(tool)

        log.info("load_data.done", run_id=state.get("run_id"), sources=len(data_sources),
                 tools=len(updated_tools), total_rows=total_rows)
        return {
            **state,
            "tools": updated_tools,
            "column_names": all_column_names,
            "row_count": total_rows,
            "action_history": [],
            "iteration_count": 0,
        }
    except Exception as exc:
        log.error("load_data.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Failed to load data: {exc}"}


def plan_action(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.llm.client import get_llm_client

        prompt = _build_plan_prompt(state)
        result = get_llm_client().complete(prompt)
        response = result.text.strip()

        prior_cost = state.get("estimated_cost_usd") or 0.0
        new_state = {
            **state,
            "llm_response": response,
            "input_tokens": state.get("input_tokens", 0) + result.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + result.output_tokens,
            "total_tokens": state.get("total_tokens", 0) + result.total_tokens,
            "estimated_cost_usd": prior_cost + (result.estimated_cost_usd or 0.0),
            "api_request_count": state.get("api_request_count", 0) + 1,
        }

        if response.upper().startswith("FINAL ANSWER:"):
            new_state["answer"] = response[len("FINAL ANSWER:"):].strip()
            log.info("plan_action.final_answer", run_id=state.get("run_id"), iterations=state.get("iteration_count", 0))
        else:
            log.info("plan_action.tool_call", run_id=state.get("run_id"),
                     iteration=state.get("iteration_count", 0), llm_response=response[:300])

        return new_state
    except Exception as exc:
        log.error("plan_action.failed", run_id=state.get("run_id"), error=str(exc))
        _cleanup_db(state.get("run_id", ""))
        return {**state, "error": f"LLM action planning failed: {exc}"}


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text


def _execute_csv_query(conn: sqlite3.Connection, sql: str) -> tuple[str, bool]:
    """Returns (result_str, is_error)."""
    if not sql.upper().lstrip().startswith("SELECT"):
        return f"Only SELECT statements are allowed. Got: {sql[:80]}", True
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(200)
        col_headers = [d[0] for d in cursor.description] if cursor.description else []
        result_lines = [",".join(col_headers)]
        for row in rows:
            result_lines.append(",".join("" if v is None else str(v) for v in row))
        return "\n".join(result_lines), False
    except sqlite3.Error as exc:
        return str(exc), True


def execute_action(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.config.settings import get_settings
        max_iterations = get_settings().max_agent_iterations

        run_id = state["run_id"]
        raw = _strip_json_fences(state.get("llm_response", ""))

        # Parse the tool call JSON
        try:
            call = json.loads(raw)
            capability_name: str = call["capability"]
            parameters: dict = call.get("parameters", {})
        except (json.JSONDecodeError, KeyError) as exc:
            _cleanup_db(run_id)
            return {**state, "error": f"LLM returned invalid tool call JSON: {exc} — raw: {raw[:200]}"}

        # Find the capability across loaded tools
        found_tool_type: str | None = None
        tools: list[dict] = state.get("tools", [])
        for tool in tools:
            for cap in tool.get("capabilities", []):
                if cap["name"] == capability_name:
                    found_tool_type = tool["type"]
                    break
            if found_tool_type:
                break

        if found_tool_type is None:
            _cleanup_db(run_id)
            return {**state, "error": f"Unknown capability: {capability_name}"}

        # Dispatch by tool type
        if found_tool_type == "csv_query" and capability_name == "run_query":
            conn = _db_cache.get(run_id)
            if conn is None:
                return {**state, "error": "In-memory DB not found — load_data must run before execute_action"}
            sql = parameters.get("query", "")
            log.debug("execute_action.sql", run_id=run_id, sql=sql)
            result_str, is_error = _execute_csv_query(conn, sql)
            if is_error:
                log.warning("execute_action.sql_error", run_id=run_id, sql=sql, error=result_str)
        else:
            _cleanup_db(run_id)
            return {**state, "error": f"No executor for tool type '{found_tool_type}' capability '{capability_name}'"}

        history = list(state.get("action_history", []))
        history.append({
            "capability": capability_name,
            "parameters": parameters,
            "result": result_str,
            "is_error": is_error,
        })
        iteration_count = state.get("iteration_count", 0) + 1

        log.info("execute_action.done", run_id=run_id, capability=capability_name,
                 iteration=iteration_count, is_error=is_error)

        new_state = {**state, "action_history": history, "iteration_count": iteration_count}

        if iteration_count >= max_iterations:
            _cleanup_db(run_id)
            return {**new_state, "error": f"Max iterations ({max_iterations}) reached without a final answer"}

        return new_state
    except Exception as exc:
        log.error("execute_action.failed", run_id=state.get("run_id"), error=str(exc))
        _cleanup_db(state.get("run_id", ""))
        return {**state, "error": f"Action execution failed: {exc}"}


def finalize(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.db.session import create_db_session
        from data_analysis_agent.db.models import QueryRecordRow, AgentRunRow
        history = state.get("action_history", [])
        with create_db_session() as db:
            qr = db.get(QueryRecordRow, state["query_record_id"])
            if qr:
                qr.answer = state.get("answer", "")
                qr.status = "completed"
                qr.iteration_count = state.get("iteration_count", 0)
                qr.query_history_json = json.dumps(history)
                qr.input_tokens = state.get("input_tokens", 0)
                qr.output_tokens = state.get("output_tokens", 0)
                qr.total_tokens = state.get("total_tokens", 0)
                qr.estimated_cost_usd = state.get("estimated_cost_usd")
                qr.api_request_count = state.get("api_request_count", 1)
            run = db.get(AgentRunRow, state["run_id"])
            if run:
                run.status = "completed"
        _cleanup_db(state["run_id"])
        log.info("finalize.done", run_id=state.get("run_id"))
        return state
    except Exception as exc:
        log.error("finalize.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Finalize failed: {exc}"}


def handle_error(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.db.session import create_db_session
        from data_analysis_agent.db.models import QueryRecordRow, AgentRunRow
        error_msg = state.get("error", "Unknown error")
        with create_db_session() as db:
            qr = db.get(QueryRecordRow, state.get("query_record_id", ""))
            if qr:
                qr.status = "failed"
                qr.error_message = error_msg
            run = db.get(AgentRunRow, state.get("run_id", ""))
            if run:
                run.status = "failed"
                run.error_message = error_msg
        log.error("pipeline.failed", run_id=state.get("run_id"), error=error_msg)
    except Exception as exc:
        log.error("handle_error.db_write_failed", error=str(exc))
    finally:
        _cleanup_db(state.get("run_id", ""))
    return state
