"""FastAPI application assembly."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hex.__version__ import __version__
from hex.api.system_routes import router as system_router
from hex.config import Settings, get_settings
from hex.database import SetupStateManager, build_engine, build_sessionmaker
from hex.database.migrate import assert_at_head, upgrade_to_head
from hex.secrets import broker_from_settings, validate_secrets
from hex.setup import AttemptLimiter

log = logging.getLogger("hex.setup")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HEx API application.

    Refuses to boot if required secrets are missing or weak (ADR 0005). Brings up the
    database and applies migrations on startup, mints the first-run setup token, then serves
    the built frontend single-origin when present. Run via uvicorn with ``--factory``.
    """
    settings = settings or get_settings()
    validate_secrets(settings)
    broker = broker_from_settings(settings)

    # Docs live at /api-docs (tucked away), not FastAPI's default /docs; ReDoc off.
    app = FastAPI(
        title="HEx",
        version=__version__,
        debug=settings.env != "production",
        docs_url="/api-docs",
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.secrets = broker
    app.state.setup_limiter = AttemptLimiter(
        settings.setup_unlock_max_attempts, settings.setup_unlock_window_seconds
    )
    app.include_router(system_router)
    _mount_spa(app, settings)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Apply migrations, open the DB, seed setup-state, mint the setup token, dispose on shutdown.

    Migrations and the engine are skipped when a test has pre-attached a sessionmaker, so the
    fast suite builds schema directly against SQLite without touching Alembic.
    """
    settings: Settings = app.state.settings
    if getattr(app.state, "sessionmaker", None) is None:
        if settings.db_auto_migrate:
            # Alembic is synchronous and its env runs its own loop; keep it off this one.
            await asyncio.to_thread(upgrade_to_head, settings)
        elif settings.env == "production":
            # Operator owns migrations here; refuse to serve against a stale schema.
            await assert_at_head(settings)
        engine = build_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)

    factory = app.state.sessionmaker
    async with factory() as session:
        manager = SetupStateManager(session)
        await manager.get_or_create()
        token = await manager.issue_setup_token()
    if token is not None:
        # The one place the plaintext appears: out-of-band retrieval from the container logs.
        log.warning("First-run setup token (enter it in the browser to begin setup): %s", token)

    yield

    owned_engine = getattr(app.state, "engine", None)
    if owned_engine is not None:
        await owned_engine.dispose()


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    """Serve the built frontend on the same origin, if present.

    No-op in dev/test where the bundle isn't built. API routes and ``/api-docs`` are
    registered first, so this catch-all mount never shadows them.
    """
    if not settings.static_dir:
        return
    static = Path(settings.static_dir)
    if not static.is_dir():
        return
    app.mount("/", StaticFiles(directory=static, html=True), name="spa")
