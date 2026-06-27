import json

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session, init_db
from db.models import RunRow


def run_agent(dataset_id: str, question: str) -> str:
    init_db()

    with create_db_session() as session:
        run = RunRow(dataset_id=dataset_id, question=question)
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "question": question,
        "error": None,
    }
    final = agentic_ai.invoke(initial)

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.chart_type = final.get("chart_type")
        run.labels_json = json.dumps(final.get("labels") or [])
        run.values_json = json.dumps(final.get("values") or [])
        run.summary = final.get("summary")
        run.error_message = final.get("error")

    return run_id
