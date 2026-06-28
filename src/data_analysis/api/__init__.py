from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from data_analysis.db.models import QueryRun
    from data_analysis.db.session import create_db_session, init_db
    from sqlalchemy import update

    from data_analysis.observability import configure_logging
    from data_analysis.config.settings import get_settings
    configure_logging(get_settings().log_level)
    init_db()
    # Mark interrupted runs on startup
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        with create_db_session() as session:
            session.execute(
                update(QueryRun)
                .where(QueryRun.status == "running")
                .where(QueryRun.started_at < cutoff)
                .values(status="interrupted")
            )
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Data Analysis Agent", version="0.1.0", lifespan=_lifespan)

    from data_analysis.api import files, health, sessions_stub, upload

    # query router will be added by the agent-graph slice in api/query.py
    try:
        from data_analysis.api import query

        app.include_router(query.router)
    except ImportError:
        pass

    app.include_router(health.router)
    app.include_router(upload.router)
    app.include_router(files.router)
    app.include_router(sessions_stub.router)

    # Serve the built Next.js static export at /app
    # __file__ is src/data_analysis/api/__init__.py
    # parent.parent.parent.parent = repo root
    frontend_out = (
        Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "out"
    )
    if frontend_out.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(frontend_out), html=True),
            name="frontend",
        )

    return app


app = create_app()
