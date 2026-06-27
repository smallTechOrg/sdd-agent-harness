from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import render
from data_analysis_agent.api._view import spa_context
from data_analysis_agent.db.session import get_session

router = APIRouter()


@router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    """Render the single-page shell with no active session/server (the Analyse tab)."""
    return render(request, templates, "index.html", **spa_context(session))
