"""GET /dashboard: ledger-driven tiles, strict per-user scoping, and the auth boundary."""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.main import create_app
from hex.database import LedgerManager, SessionManager, SetupStateManager, User
from hex.providers.types import ProvisionState
from tests.conftest import make_settings
from tests.providers.reference import ReferenceLocalProvider

SESSION_COOKIE = "hex_session"


async def _dashboard(client: AsyncClient, cookie: str | None = None) -> Response:
    # Cookie via header (not per-request cookies=, which httpx deprecates) so one client serves
    # several distinct users without cross-contaminating a persisted cookie jar.
    headers = {"Cookie": f"{SESSION_COOKIE}={cookie}"} if cookie else {}
    return await client.get("/dashboard", headers=headers)


async def _user(sessionmaker: async_sessionmaker[AsyncSession], sub: str) -> int:
    async with sessionmaker() as session:
        user = User(authentik_sub=sub, username=sub)
        session.add(user)
        await session.flush()
        uid = user.id
        await session.commit()
    return uid


async def _session_cookie(sessionmaker: async_sessionmaker[AsyncSession], uid: int) -> str:
    async with sessionmaker() as session:
        user = await session.get(User, uid)
        assert user is not None
        raw = await SessionManager(session, lifetime_seconds=3600).create(user)
        await session.commit()
    return raw


async def _grant(
    sessionmaker: async_sessionmaker[AsyncSession],
    uid: int,
    provider_id: str,
    state: ProvisionState = ProvisionState.GRANTED,
) -> None:
    async with sessionmaker() as session:
        await LedgerManager(session).record_event(user_id=uid, provider_id=provider_id, state=state)
        await session.commit()


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    # dev_providers wires demo-media + demo-requests; env=dev for a non-Secure cookie over http://.
    app = create_app(make_settings(env="dev", dev_providers=True))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    assert (await _dashboard(client)).status_code == 401


async def test_dashboard_rejects_a_forged_cookie(client: AsyncClient) -> None:
    # A present-but-bogus session token must resolve to no user (fail-secure), not leak a dashboard.
    assert (await _dashboard(client, "not-a-real-session-token")).status_code == 401


async def test_dashboard_empty_when_no_grants(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    uid = await _user(sessionmaker, "fresh")
    cookie = await _session_cookie(sessionmaker, uid)
    resp = await _dashboard(client, cookie)
    assert resp.status_code == 200
    assert resp.json() == {"tiles": []}


async def test_dashboard_lists_granted_resolvable_tiles(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    uid = await _user(sessionmaker, "user")
    await _grant(sessionmaker, uid, "demo-media")
    cookie = await _session_cookie(sessionmaker, uid)
    tiles = (await _dashboard(client, cookie)).json()["tiles"]
    assert len(tiles) == 1
    tile = tiles[0]
    assert tile["provider_id"] == "demo-media"
    assert tile["name"] == "Demo Media"
    assert tile["category"] == "media"
    assert tile["state"] == "granted"
    assert tile["integration_mode"] == "sso_group"
    assert tile["url"] == "https://media.demo.hex.local"
    assert tile["seamless"] is True


async def test_dashboard_omits_unregistered_provider(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    uid = await _user(sessionmaker, "user")
    await _grant(sessionmaker, uid, "demo-media")
    await _grant(sessionmaker, uid, "ghost-service")  # not in the registry
    cookie = await _session_cookie(sessionmaker, uid)
    tiles = (await _dashboard(client, cookie)).json()["tiles"]
    assert {t["provider_id"] for t in tiles} == {"demo-media"}


async def test_dashboard_omits_inactive_grants(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    uid = await _user(sessionmaker, "user")
    await _grant(sessionmaker, uid, "demo-media")
    await _grant(sessionmaker, uid, "demo-media", ProvisionState.REVOKED)  # latest event wins
    cookie = await _session_cookie(sessionmaker, uid)
    tiles = (await _dashboard(client, cookie)).json()["tiles"]
    assert tiles == []


async def test_dashboard_never_leaks_another_users_tiles(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    alice = await _user(sessionmaker, "alice")
    bob = await _user(sessionmaker, "bob")
    await _grant(sessionmaker, alice, "demo-media")
    await _grant(sessionmaker, bob, "demo-requests")
    alice_cookie = await _session_cookie(sessionmaker, alice)
    bob_cookie = await _session_cookie(sessionmaker, bob)

    alice_tiles = (await _dashboard(client, alice_cookie)).json()
    bob_tiles = (await _dashboard(client, bob_cookie)).json()
    assert {t["provider_id"] for t in alice_tiles["tiles"]} == {"demo-media"}
    assert {t["provider_id"] for t in bob_tiles["tiles"]} == {"demo-requests"}


async def test_dashboard_pending_tile_is_shown_but_not_linked(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    uid = await _user(sessionmaker, "user")
    await _grant(sessionmaker, uid, "demo-media", ProvisionState.PENDING_MANUAL)
    cookie = await _session_cookie(sessionmaker, uid)
    tiles = (await _dashboard(client, cookie)).json()["tiles"]
    assert len(tiles) == 1
    assert tiles[0]["state"] == "pending_manual"
    assert tiles[0]["url"] is None  # not live yet → no click-through to access the user lacks


async def test_dashboard_tile_without_link_and_non_sso_mode(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # ReferenceLocalProvider exposes no `link` and is api_local (not sso_group) → url None, seamless
    # False. Proves the negative branches of _tile_url / the seamless comparison server-side.
    app = create_app(make_settings(env="dev", dev_providers=True))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.registry.register(ReferenceLocalProvider())
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()
    uid = await _user(sessionmaker, "user")
    await _grant(sessionmaker, uid, "ref-local")
    cookie = await _session_cookie(sessionmaker, uid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        tiles = (await _dashboard(ac, cookie)).json()["tiles"]
    tile = next(t for t in tiles if t["provider_id"] == "ref-local")
    assert tile["url"] is None
    assert tile["seamless"] is False
