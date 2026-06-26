import json

from fastapi import APIRouter

from api._common import ok, api_error
from db.session import create_db_session
from db.models import UploadSession, QueryRun
from domain.run import QueryRequest, QueryResponse
from graph.agent import agentic_ai
from observability.events import get_logger

router = APIRouter()
_log = get_logger("api.query")


@router.post("/query")
def run_query(req: QueryRequest) -> dict:
    session_id = req.session_id
    question = req.question

    # Validate question length
    if not question or len(question.strip()) == 0 or len(question) > 2000:
        raise api_error("VALIDATION_ERROR", "Question must be 1–2000 characters.", 422)

    # Look up the upload session
    with create_db_session() as session:
        upload_session = session.get(UploadSession, session_id)
        if upload_session is None:
            raise api_error("SESSION_NOT_FOUND", f"Session {session_id} not found.", 404)
        table_name = upload_session.table_name

        # Create a pending QueryRun
        query_run = QueryRun(
            session_id=session_id,
            question=question,
            status="pending",
        )
        session.add(query_run)
        session.flush()
        run_id = query_run.id

    _log.info("query.start", run_id=run_id, session_id=session_id, question=question[:80])

    # Build initial state and invoke the pipeline
    initial_state = {
        "run_id": run_id,
        "session_id": session_id,
        "table_name": table_name,
        "question": question,
    }
    final_state = agentic_ai.invoke(initial_state)

    # Persist results
    with create_db_session() as session:
        query_run = session.get(QueryRun, run_id)
        if query_run is not None:
            query_run.sql = final_state.get("sql")
            chart_spec = final_state.get("chart_spec")
            query_run.chart_spec = json.dumps(chart_spec) if chart_spec is not None else None
            query_run.insight = final_state.get("insight")
            query_run.status = final_state.get("status", "completed")
            query_run.error = final_state.get("error")

    # Build response
    chart_spec_out = None
    raw_chart = final_state.get("chart_spec")
    if raw_chart is not None:
        chart_spec_out = raw_chart

    _log.info("query.done", run_id=run_id, status=final_state.get("status"))

    return ok(
        QueryResponse(
            query_run_id=run_id,
            status=final_state.get("status", "completed"),
            sql=final_state.get("sql"),
            chart_spec=chart_spec_out,
            insight=final_state.get("insight"),
            error=final_state.get("error"),
        ).model_dump()
    )
