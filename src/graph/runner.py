from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session, init_db
from db.models import QuestionRow


def run_agent(dataset_id: str, question: str) -> str:
    """Run one DataChat question end-to-end.

    Creates the QuestionRow (status="pending"), invokes the graph, and lets
    ``finalize``/``handle_error`` persist the result onto that same row (looked
    up by ``run_id``). Returns the question_id.
    """
    init_db()

    with create_db_session() as session:
        q = QuestionRow(dataset_id=dataset_id, question=question, status="pending")
        session.add(q)
        session.flush()
        question_id = q.id

    initial: AgentState = {
        "run_id": question_id,
        "dataset_id": dataset_id,
        "question": question,
        "error": None,
        "messages": [],
    }
    agentic_ai.invoke(initial)

    return question_id
