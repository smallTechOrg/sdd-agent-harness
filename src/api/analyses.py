from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import api_error, ok
from db.models import AnalysisRow, DatasetRow
from db.session import get_session
from domain.analysis import AnalysisRequest, AnalysisResponse
from graph.runner import run_analysis
from observability.events import get_logger

router = APIRouter()
log = get_logger("api.analyses")


@router.post("/analyses")
def create_analysis(
    req: AnalysisRequest,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(DatasetRow, req.dataset_id)
    if ds is None:
        raise api_error("NOT_FOUND", f"Dataset {req.dataset_id} not found", 404)
    if ds.status != "ready":
        raise api_error(
            "DATASET_NOT_READY",
            f"Dataset {req.dataset_id} is not ready (status={ds.status}).",
            409,
        )

    log.info(
        "analysis.requested",
        dataset_id=req.dataset_id,
        question=req.question,
    )

    try:
        run_id = run_analysis(req.dataset_id, req.question)
    except ValueError as exc:
        # run_analysis raises ValueError only when the dataset id is unknown,
        # which we already guarded — treat as a not-found race.
        raise api_error("NOT_FOUND", str(exc), 404)
    except Exception as exc:  # noqa: BLE001 — unexpected failure -> 500
        log.info("analysis.unexpected_error", dataset_id=req.dataset_id, error=str(exc))
        raise api_error(
            "ANALYSIS_FAILED",
            f"Analysis failed unexpectedly: {exc}",
            500,
        )

    row = session.get(AnalysisRow, run_id)
    if row is None:
        raise api_error(
            "ANALYSIS_FAILED",
            "Analysis row missing after run.",
            500,
        )

    log.info("analysis.completed", analysis_id=run_id, status=row.status)

    # A retries-exhausted run is returned as a 200 with status=failed body so the
    # frontend can display the plain-language failure gracefully. Only unexpected
    # exceptions (above) become a 500 ANALYSIS_FAILED.
    return ok(AnalysisResponse.from_row(row).model_dump())


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: str,
    session: Session = Depends(get_session),
) -> dict:
    row = session.get(AnalysisRow, analysis_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Analysis {analysis_id} not found", 404)
    return ok(AnalysisResponse.from_row(row).model_dump())
