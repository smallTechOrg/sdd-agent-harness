from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from db.session import init_db
    init_db()

    # Seed the DuckDB sample dataset so the live server has the `sales` table.
    # Idempotent and non-fatal: a seed failure must not crash startup.
    try:
        from analytics.seed import seed_sales
        seed_sales()
    except Exception as exc:  # pragma: no cover - defensive startup guard
        from observability.events import get_logger
        get_logger("api.startup").error("seed_sales_startup_failed", error=str(exc))

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Agent", version="0.1.0", lifespan=_lifespan)
    from api import health, runs
    app.include_router(health.router)
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
