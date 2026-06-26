from fastapi import APIRouter

from api._common import ok

router = APIRouter()


def _provider_name() -> str:
    """Resolve the active LLM provider for the UI stub banner.

    Wrapped so a provider-init issue never 500s `/health` — any exception falls
    back to `stub` (the offline default).
    """
    try:
        from llm.client import LLMClient
        return LLMClient().provider
    except Exception:
        return "stub"


@router.get("/health")
def health() -> dict:
    return ok({"status": "ok", "provider": _provider_name()})
