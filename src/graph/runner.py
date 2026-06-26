import json

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session, init_db
from db.models import RunRow


def _compact_output(answer: str | None, explanation: str | None) -> str | None:
    """A back-compat summary stored in output_text (answer + explanation)."""
    parts = [p for p in (answer, explanation) if p]
    if not parts:
        return None
    if answer and explanation and explanation != answer:
        return f"{answer}\n\n{explanation}"
    return parts[0]


def run_agent(csv_text: str, question: str) -> str:
    init_db()

    with create_db_session() as session:
        run = RunRow(status="pending", input_text=question, question=question)
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {
        "run_id": run_id,
        "csv_text": csv_text,
        "question": question,
        "retry_count": 0,
        "error": None,
    }
    final = agentic_ai.invoke(initial)

    answer = final.get("answer")
    explanation = final.get("explanation")
    result_table = final.get("result_table")

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.generated_code = final.get("generated_code")
        run.answer = answer
        run.explanation = explanation
        run.result_table = json.dumps(result_table) if result_table is not None else None
        run.output_text = _compact_output(answer, explanation)
        run.error_message = final.get("error")

    return run_id
