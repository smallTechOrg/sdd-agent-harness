from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/sessions")
def list_sessions():
    """Phase 1 stub — returns empty list. Real implementation in Phase 2."""
    return {"sessions": []}
