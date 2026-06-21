"""System route tests."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.__version__ import __version__
from hex.api.main import create_app
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
