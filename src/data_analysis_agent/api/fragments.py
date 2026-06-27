"""HTML-fragment endpoints backing the UI's "Load more" buttons.

Each returns the next ``ui_page_size`` window of one list, rendered with the SAME row macros as the
inline first page (``_partials.html`` via ``fragments.html``) plus a fresh Load-more button when more
remain. The client (``loadMore`` / ``loadOlderQueries`` in ``index.html``) splices the returned HTML in
place of the clicked button, so a paged-in row is identical to a server-rendered one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._repository import get_database_or_404, get_session_or_404
from data_analysis_agent.api._view import (
    paged_capability,
    paged_databases,
    paged_queries,
    paged_sessions,
)
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import McpPromptRow, McpResourceRow, McpToolRow
from data_analysis_agent.db.session import get_session

router = APIRouter(prefix="/fragments")

_CAP_MODELS = {"tools": McpToolRow, "resources": McpResourceRow, "prompts": McpPromptRow}


def _next_url(path: str, offset: int, has_more: bool) -> str | None:
    """The URL for the page after the one starting at ``offset`` (or ``None`` when exhausted)."""
    if not has_more:
        return None
    return f"{path}?offset={offset + get_settings().ui_page_size}"


def _render(request: Request, kind: str, items: list, next_url: str | None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "fragments.html", {"kind": kind, "items": items, "next_url": next_url}
    )


@router.get("/sessions")
def frag_sessions(request: Request, offset: int = 0, session: Session = Depends(get_session)):
    items, more = paged_sessions(session, offset, None)
    return _render(request, "sessions", items, _next_url("/fragments/sessions", offset, more))


@router.get("/databases")
def frag_databases(request: Request, offset: int = 0, session: Session = Depends(get_session)):
    items, more = paged_databases(session, offset)
    return _render(request, "databases", items, _next_url("/fragments/databases", offset, more))


@router.get("/database/{database_id}/{kind}")
def frag_capability(
    request: Request,
    database_id: str,
    kind: str,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Next page of a database's tools / resources / prompts."""
    model = _CAP_MODELS.get(kind)
    if model is None:
        return HTMLResponse("", status_code=404)
    get_database_or_404(session, database_id)
    items, more = paged_capability(session, model, database_id, offset)
    return _render(request, kind, items, _next_url(f"/fragments/database/{database_id}/{kind}", offset, more))


@router.get("/sessions/{session_id}/queries")
def frag_queries(
    request: Request,
    session_id: str,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Older turns of a session's chat thread (chronological window; ``has_more`` = even older exist)."""
    get_session_or_404(session, session_id)
    items, more = paged_queries(session, session_id, offset)
    return _render(request, "queries", items,
                   _next_url(f"/fragments/sessions/{session_id}/queries", offset, more))
