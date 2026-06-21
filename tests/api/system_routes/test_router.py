"""System route tests."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from hex.__version__ import __version__
from hex.api.main import create_app
from hex.database import SetupStateManager, build_sessionmaker
from hex.database.models import SetupPhase, SetupState
from tests.conftest import make_settings


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


async def test_setup_status_reports_first_run(client: AsyncClient) -> None:
    resp = await client.get("/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"phase": "first_run", "setup_required": True}
    # Exact shape: nothing beyond these two keys can leak through the surface.
    assert set(body) == {"phase", "setup_required"}


async def test_setup_status_reports_complete(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:  # shares the client's engine
        state = await session.get(SetupState, 1)
        assert state is not None
        state.phase = SetupPhase.COMPLETE
        await session.commit()

    resp = await client.get("/setup/status")
    assert resp.json() == {"phase": "complete", "setup_required": False}


async def test_setup_status_first_run_when_row_absent(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """No setup-state row yet → fail-secure default of first_run, not a 500."""
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker  # schema present, row deliberately not seeded

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/setup/status")

    assert resp.status_code == 200
    assert resp.json() == {"phase": "first_run", "setup_required": True}


async def test_setup_status_returns_503_when_db_unavailable() -> None:
    """A DB error surfaces as 503, not a debug 500 with a stack trace."""
    eng = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    app = create_app(make_settings())
    app.state.engine = eng
    app.state.sessionmaker = build_sessionmaker(eng)  # schema never built → query fails

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/setup/status")
    await eng.dispose()

    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}


async def test_setup_unlock_advances_with_correct_token(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        token = await SetupStateManager(session).issue_setup_token()
    assert token is not None

    resp = await client.post("/setup/unlock", json={"token": token})
    assert resp.status_code == 200
    assert resp.json() == {"phase": "bootstrap", "setup_required": True}


async def test_setup_unlock_rejects_wrong_token_uniformly(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        await SetupStateManager(session).issue_setup_token()

    resp = await client.post("/setup/unlock", json={"token": "not-the-token"})
    assert resp.status_code == 401
    # Wrong / absent / already-consumed all read the same — no enumeration signal.
    assert resp.json() == {"detail": "invalid setup token"}


async def test_setup_unlock_rejects_when_no_token_issued(client: AsyncClient) -> None:
    resp = await client.post("/setup/unlock", json={"token": "anything"})
    assert resp.status_code == 401


async def test_setup_unlock_throttles_repeated_attempts(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings(setup_unlock_max_attempts=2))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [
            (await client.post("/setup/unlock", json={"token": "x"})).status_code for _ in range(3)
        ]
    assert codes == [401, 401, 429]


async def test_setup_unlock_success_does_not_consume_throttle_budget(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A correct token must not cost budget: under a 1-failure limit, unlock then retry is 401."""
    app = create_app(make_settings(setup_unlock_max_attempts=1))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        token = await SetupStateManager(session).issue_setup_token()
    assert token is not None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        good = await client.post("/setup/unlock", json={"token": token})
        # If success had consumed the single slot, this would be pre-empted with 429.
        after = await client.post("/setup/unlock", json={"token": "x"})
    assert good.status_code == 200
    assert after.status_code == 401


async def test_setup_unlock_returns_503_when_db_unavailable() -> None:
    """A DB error during unlock surfaces as 503, not a debug 500 (matches /setup/status)."""
    eng = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    app = create_app(make_settings())
    app.state.engine = eng
    app.state.sessionmaker = build_sessionmaker(eng)  # schema never built → query fails

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/setup/unlock", json={"token": "anything"})
    await eng.dispose()

    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}
