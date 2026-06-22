from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def ok(data: Any) -> dict:
    """Wrap a successful payload in the standard ``{data, error}`` envelope."""
    return {"data": data, "error": None}


def api_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    """Build an ``HTTPException`` carrying a structured ``{code, message}`` detail."""
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def render(request: Request, templates: Jinja2Templates, name: str, **ctx) -> HTMLResponse:
    """Render a template, injecting the request and resolved LLM provider into context."""
    from data_analysis_agent.config.settings import get_settings
    ctx["llm_provider"] = get_settings().resolved_llm_provider
    ctx["request"] = request
    return templates.TemplateResponse(request, name, ctx)
