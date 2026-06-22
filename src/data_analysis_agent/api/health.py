from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health_check() -> JSONResponse:
    """Return a static ``{"status": "ok"}`` payload for liveness checks."""
    return JSONResponse({"status": "ok"})
