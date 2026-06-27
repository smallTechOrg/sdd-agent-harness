from config.settings import get_settings
from db.models import AnalysisRow, DatasetRow
from db.session import create_db_session, init_db
from graph.agent import agentic_ai
from graph.state import AgentState
from observability.events import get_logger

log = get_logger("graph.runner")


def run_analysis(dataset_id: str, question: str) -> str:
    """Run the code-interpreter analysis loop for one question on one dataset.

    Loads dataset metadata (local path + bounded schema summary) from the
    ``datasets`` table, creates an ``analyses`` row (status=pending), invokes the
    graph, persists generated_code / execution_result / execution_steps / answer /
    attempts / status / error_message back to that row, and returns its id (run_id).
    """
    init_db()

    with create_db_session() as session:
        ds = session.get(DatasetRow, dataset_id)
        if ds is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        schema_summary = ds.schema_summary or ""
        dataframe_path = ds.local_path

        analysis = AnalysisRow(
            dataset_id=dataset_id,
            question=question,
            status="pending",
        )
        session.add(analysis)
        session.flush()
        run_id = analysis.id

    log.info("analysis.started", run_id=run_id, dataset_id=dataset_id)

    initial: AgentState = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "question": question,
        "schema_summary": schema_summary,
        "dataframe_path": dataframe_path,
        "attempts": 0,
        "max_attempts": get_settings().max_attempts,
        "error": None,
    }

    final: AgentState = agentic_ai.invoke(initial)

    with create_db_session() as session:
        row = session.get(AnalysisRow, run_id)
        row.generated_code = final.get("generated_code")
        row.execution_result = final.get("execution_result")
        row.execution_steps = final.get("execution_steps")
        row.answer = final.get("answer")
        row.attempts = final.get("attempts", 0)
        row.status = final.get("status", "completed")
        row.error_message = final.get("error")

    log.info(
        "analysis.finished",
        run_id=run_id,
        status=final.get("status"),
        attempts=final.get("attempts"),
    )
    return run_id
