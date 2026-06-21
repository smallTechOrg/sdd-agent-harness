from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="src/api/templates")


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(request, name, {"stub_mode": settings.is_stub, **ctx})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return render(request, "index.html")


@router.post("/run", response_class=HTMLResponse)
async def run(request: Request):
    form = await request.form()
    user_input = (form.get("input") or "").strip()
    if not user_input:
        return render(request, "index.html", error="Please enter a request.")
    try:
        from src.agent.graph import graph
        from src.agent.state import AgentState
        state: AgentState = {
            "run_id": 0,
            "user_input": user_input,
            "tool_call_history": [],
            "result": None,
            "error": None,
            "iterations": 0,
        }
        final = await graph.ainvoke(state)
        if final.get("error"):
            return render(request, "index.html", input=user_input, error=final["error"])
        return render(request, "index.html", input=user_input, result=final.get("result", ""))
    except Exception as exc:
        return render(request, "index.html", input=user_input, error=str(exc))
