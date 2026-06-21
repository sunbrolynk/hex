"""Async engine, session factory, and the request-scoped session dependency."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hex.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine for the configured DSN."""
    # pool_pre_ping survives Postgres restarts/idle drops without surfacing stale connections.
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session from the app's session factory."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with factory() as session:
        yield session
