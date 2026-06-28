import json
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

from data_analysis.db.models import QueryRun
from data_analysis.db.session import create_db_session
from data_analysis.graph.agent import compiled_graph
from data_analysis.graph.state import AnalysisState


def run_analysis_stream(
    question: str,
    file_ids: list[str],
    session_id: str | None = None,
) -> Generator[str, None, None]:
    """
    Run the analysis graph and yield SSE-formatted event strings.
    Each yielded string is a complete SSE 'data: {...}\\n\\n' line.
    """
    query_run_id = str(uuid.uuid4())
    sse_events: list[str] = []

    def emit(event_type: str, data: dict) -> None:
        """Callback invoked by graph nodes to queue SSE events."""
        sse_events.append(json.dumps(data))

    # Create the QueryRun row
    try:
        with create_db_session() as session:
            run = QueryRun(
                id=query_run_id,
                session_id=session_id,
                file_ids=json.dumps(file_ids),
                question=question,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
    except Exception:
        pass

    # Emit run_start immediately so the client knows we started
    yield f"data: {json.dumps({'type': 'run_start', 'query_run_id': query_run_id})}\n\n"

    # Build initial state
    initial_state: AnalysisState = {
        "query_run_id": query_run_id,
        "question": question,
        "file_ids": file_ids,
        "session_id": session_id,
        "profiles": [],
        "data_paths": [],
        "plan": "",
        "iteration": 0,
        "max_iterations": 5,
        "execution_history": [],
        "last_execution_result": None,
        "last_execution_error": None,
        "needs_clarification": False,
        "clarification_question": None,
        "answer_text": None,
        "plotly_chart": None,
        "followup_suggestions": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "error": None,
        "checkpoint": None,
        "_sse_emit": emit,
        "_generated_code": None,
    }

    # Run the graph synchronously
    try:
        compiled_graph.invoke(initial_state)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Yield all queued SSE events
    for event_json in sse_events:
        yield f"data: {event_json}\n\n"

    # Guarantee a done event if none was emitted
    if not sse_events or not any('"done"' in ev for ev in sse_events):
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
