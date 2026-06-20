"""FastAPI application assembly."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hex.__version__ import __version__
from hex.api.system_routes import router as system_router
from hex.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HEx API application.

    Slice 0 wires the system router and, when a built frontend bundle is present,
    serves it on the same origin (single port). Auth, security headers, and the
    other route groups land in later slices.
    """
    settings = settings or get_settings()
    # Docs live at /api-docs (tucked away), not FastAPI's default /docs; ReDoc off.
    app = FastAPI(
        title="HEx",
        version=__version__,
        debug=settings.env != "production",
        docs_url="/api-docs",
        redoc_url=None,
    )
    app.include_router(system_router)
    _mount_spa(app, settings)
    return app


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    """Serve the built frontend on the same origin, if it is present.

    No-op in dev/test where the bundle isn't built. API routes and ``/api-docs`` are
    registered first, so this catch-all mount never shadows them.
    """
    if not settings.static_dir:
        return
    static = Path(settings.static_dir)
    if not static.is_dir():
        return
    app.mount("/", StaticFiles(directory=static, html=True), name="spa")


app = create_app()
