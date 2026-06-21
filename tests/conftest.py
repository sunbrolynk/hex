"""Shared test fixtures."""

import base64
import os
import secrets
from collections.abc import AsyncIterator

# Seed valid secrets before any Settings() is built, so create_app() passes boot validation.
# Refuse-to-boot abuse cases pass crafted Settings directly (see tests/secrets, tests/api).
os.environ.setdefault("HEX_SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("HEX_KEK", base64.b64encode(secrets.token_bytes(32)).decode())
os.environ.setdefault("HEX_AUDIT_KEY", secrets.token_urlsafe(48))
os.environ.setdefault("HEX_DB_PASSWORD", secrets.token_urlsafe(32))
os.environ.setdefault("HEX_PROXY_SHARED_SECRET", secrets.token_urlsafe(48))

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from hex.api.main import create_app  # noqa: E402
from hex.config import Settings  # noqa: E402
from hex.database import Base, SetupStateManager, build_sessionmaker  # noqa: E402


def make_settings(**overrides: object) -> Settings:
    """Valid in-process settings; DB auto-migrate off (tests build schema directly)."""
    base: dict[str, object] = {
        "secret_key": secrets.token_urlsafe(64),
        "kek": base64.b64encode(secrets.token_bytes(32)).decode(),
        "audit_key": secrets.token_urlsafe(48),
        "db_password": secrets.token_urlsafe(32),
        "proxy_shared_secret": secrets.token_urlsafe(48),
        "db_auto_migrate": False,
    }
    return Settings.model_validate(base | overrides)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite shared across sessions (StaticPool), schema built from metadata."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_sessionmaker(engine)


@pytest_asyncio.fixture
async def db_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """HTTP client bound in-process to an app with the test DB attached (no network)."""
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
