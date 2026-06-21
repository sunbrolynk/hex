"""Startup lifespan: seeds the setup-state row and disposes the engine."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hex.api import main
from hex.api.main import create_app
from hex.database import Base, SetupStateManager
from hex.database.models import SetupPhase
from tests.conftest import make_settings


async def test_lifespan_initializes_setup_state(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker  # pre-attached → lifespan skips migrate/connect

    async with app.router.lifespan_context(app):
        async with sessionmaker() as session:
            assert await SetupStateManager(session).current_phase() is SetupPhase.FIRST_RUN


async def test_lifespan_production_branch_migrates_builds_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """No pre-attached sessionmaker → exercise the real migrate/build/dispose path on SQLite."""
    db = tmp_path / "lifespan.db"  # type: ignore[operator]
    async_url = f"sqlite+aiosqlite:///{db}"

    def fake_migrate(_: object) -> None:
        sync = create_engine(f"sqlite:///{db}")
        Base.metadata.create_all(sync)
        sync.dispose()

    built = create_async_engine(async_url)
    disposed: list[AsyncEngine] = []
    original_dispose = AsyncEngine.dispose

    async def spy_dispose(self: AsyncEngine, close: bool = True) -> None:
        disposed.append(self)
        await original_dispose(self, close)

    monkeypatch.setattr(main, "upgrade_to_head", fake_migrate)
    monkeypatch.setattr(main, "build_engine", lambda _: built)
    monkeypatch.setattr(AsyncEngine, "dispose", spy_dispose)

    app = create_app(make_settings(db_auto_migrate=True))
    assert getattr(app.state, "sessionmaker", None) is None

    async with app.router.lifespan_context(app):
        assert app.state.engine is built
        async with app.state.sessionmaker() as session:
            assert await SetupStateManager(session).current_phase() is SetupPhase.FIRST_RUN

    assert built in disposed  # engine disposed on shutdown
