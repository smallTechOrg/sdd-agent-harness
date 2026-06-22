from agent.graph.agent import agentic_ai
from agent.graph.state import AgentState
from agent.db.session import create_db_session, init_db
from agent.db.models import RunRow


def run_agent(input_text: str) -> str:
    init_db()

    with create_db_session() as session:
        run = RunRow(input_text=input_text)
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {"run_id": run_id, "input_text": input_text, "error": None}
    final = agentic_ai.invoke(initial)

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.output_text = final.get("output_text")
        run.error_message = final.get("error")

    return run_id
