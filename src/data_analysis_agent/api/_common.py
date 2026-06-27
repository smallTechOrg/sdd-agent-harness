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
    """Render a template, injecting the request and resolved LLM provider into context.

    The SPA shell is a live dashboard — its lists mutate on every create/delete/sync — so the response
    is marked ``no-store``. Without it a browser may serve a cached copy after the post-delete 303
    redirect, leaving a just-deleted session/database still in the list (clicking it then 404s).
    """
    from data_analysis_agent.config.settings import get_settings
    ctx["llm_provider"] = get_settings().resolved_llm_provider
    ctx["request"] = request
    response = templates.TemplateResponse(request, name, ctx)
    response.headers["Cache-Control"] = "no-store"
    return response
