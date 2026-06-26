from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from db.session import init_db
    init_db()
    # Ensure the uploads dir exists so the first upload never races a missing dir.
    (Path(__file__).resolve().parent.parent.parent / "uploads").mkdir(
        parents=True, exist_ok=True
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Agent", version="0.1.0", lifespan=_lifespan)
    from api import ask, datasets, health, runs, stats, upload
    app.include_router(health.router)
    app.include_router(upload.router)
    app.include_router(datasets.router)
    app.include_router(ask.router)
    app.include_router(stats.router)
    app.include_router(runs.router)

    # Serve the built Next.js static export at /app
    # Run `cd frontend && pnpm build` to generate frontend/out/ before starting.
    # Server starts fine without it (API-only mode when out/ doesn't exist).
    # __file__ = src/api/__init__.py → 3 parents up = repo root
    frontend_out = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
    if frontend_out.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_out), html=True), name="frontend")

    return app


app = create_app()
