from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Configure logging, ensure the upload dir and schema exist, then run the app."""
    from data_analysis_agent.db.session import init_db
    from data_analysis_agent.config.settings import get_settings
    from data_analysis_agent.logging_config import configure_logging
    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_file=settings.log_file)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.checkpoint_db).parent.mkdir(parents=True, exist_ok=True)
    init_db()
    yield
    from data_analysis_agent.tools.mcp.pool import get_manager
    get_manager().close_all()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application with all domain routers.

    Returns:
        The configured :class:`FastAPI` instance.
    """
    app = FastAPI(
        title="Data Analysis Agent",
        version="0.1.0",
        lifespan=_lifespan,
    )

    from data_analysis_agent.api import datasources, health, home, queries, sessions
    for module in (health, home, datasources, sessions, queries):
        app.include_router(module.router)

    return app


app = create_app()
