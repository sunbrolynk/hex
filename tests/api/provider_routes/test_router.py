"""GET /providers: owner-only catalog of grantable services + their tiers."""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.main import create_app
from hex.database import SessionManager, User
from hex.database.models import SetupPhase, SetupState
from tests.conftest import make_settings
from tests.providers.reference import ReferenceLocalProvider

SESSION_COOKIE = "hex_session"


async def _cookie(sessionmaker: async_sessionmaker[AsyncSession], *, is_owner: bool = True) -> str:
    async with sessionmaker() as session:
        if await session.get(SetupState, 1) is None:
            session.add(SetupState(id=1, phase=SetupPhase.COMPLETE))
        user = User(authentik_sub="o", username="o", is_owner=is_owner)
        session.add(user)
        await session.flush()
        raw = await SessionManager(session, lifetime_seconds=3600).create(user)
        await session.commit()
    return raw


async def _get(client: AsyncClient, cookie: str | None = None) -> Response:
    headers = {"Cookie": f"{SESSION_COOKIE}={cookie}"} if cookie else {}
    return await client.get("/providers", headers=headers)


async def _seed_setup(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        if await session.get(SetupState, 1) is None:
            session.add(SetupState(id=1, phase=SetupPhase.COMPLETE))
            await session.commit()


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(env="dev"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.registry.register(ReferenceLocalProvider())  # tiers: standard, premium
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_providers_requires_auth(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_setup(sessionmaker)
    assert (await _get(client)).status_code == 401


async def test_providers_forbidden_for_non_owner(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    cookie = await _cookie(sessionmaker, is_owner=False)
    assert (await _get(client, cookie)).status_code == 403  # owner boundary


async def test_providers_lists_registered_with_tiers(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    cookie = await _cookie(sessionmaker)
    resp = await _get(client, cookie)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    p = body[0]
    assert p["id"] == "ref-local"
    assert p["name"] == "Reference (local)"
    assert p["category"] == "test"
    assert p["integration_mode"] == "api_local"
    tiers = {t["key"]: t for t in p["tiers"]}
    assert set(tiers) == {"standard", "premium"}
    assert tiers["premium"]["label"] == "Premium"
    assert tiers["premium"]["description"] == "Full access"  # description passthrough
    assert tiers["standard"]["description"] is None


async def test_providers_forbidden_before_setup_complete(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # The owner-only catalog is gated behind setup completion, even for a valid owner session.
    app = create_app(make_settings(env="dev"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.registry.register(ReferenceLocalProvider())
    async with sessionmaker() as session:
        session.add(SetupState(id=1, phase=SetupPhase.FIRST_RUN))  # setup NOT complete
        user = User(authentik_sub="o", username="o", is_owner=True)
        session.add(user)
        await session.flush()
        raw = await SessionManager(session, lifetime_seconds=3600).create(user)
        await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/providers", headers={"Cookie": f"{SESSION_COOKIE}={raw}"})
    assert resp.status_code == 403


async def test_providers_empty_when_registry_empty(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    app = create_app(make_settings(env="dev"))  # no providers registered
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    cookie = await _cookie(sessionmaker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/providers", headers={"Cookie": f"{SESSION_COOKIE}={cookie}"})
    assert resp.status_code == 200
    assert resp.json() == []
