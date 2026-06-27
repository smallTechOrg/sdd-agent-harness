from graph.agent import agentic_ai
from graph.state import AnalysisState
from db.session import create_db_session, init_db
from db.models import RunRow


def run_agent(session_id: str, question: str) -> str:
    """
    Create a RunRow, invoke the analysis graph, and return the run_id.

    The finalize and handle_error nodes update RunRow directly;
    this function does NOT update RunRow after graph invocation.
    """
    init_db()

    with create_db_session() as session:
        run = RunRow(
            session_id=session_id,
            question=question,
            input_text=question,
            status="pending",
        )
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AnalysisState = {
        "run_id": run_id,
        "session_id": session_id,
        "question": question,
        "input_text": question,
        "error": None,
        "messages": [],
    }
    agentic_ai.invoke(initial)

    return run_id
