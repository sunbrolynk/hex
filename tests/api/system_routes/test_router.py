"""System route tests."""

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from hex.__version__ import __version__
from hex.api.main import create_app
from hex.authentik.names import SA_TOKEN_IDENTIFIER
from hex.database import (
    AuditLogManager,
    AuthentikIntegrationManager,
    SetupStateManager,
    build_sessionmaker,
)
from hex.database.models import AuditLogEntry, SetupPhase, SetupState
from tests.conftest import make_settings

_AK = "http://ak.test"
_AK_API = f"{_AK}/api/v3"


def _mock_authentik_happy() -> None:
    """Mock the full Authentik surface a successful wire touches. Call inside respx.mock."""
    respx.get(f"{_AK}/-/health/ready/").mock(return_value=httpx.Response(204))
    respx.get(f"{_AK_API}/core/applications/").mock(
        return_value=httpx.Response(200, json={"results": [{"slug": "hex", "name": "HEx"}]})
    )
    respx.get(f"{_AK_API}/providers/oauth2/").mock(
        return_value=httpx.Response(
            200, json={"results": [{"pk": 7, "name": "HEx web BFF", "client_id": "cid"}]}
        )
    )
    respx.get(f"{_AK_API}/core/groups/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": 3, "name": "HEx Provisioners"}]})
    )
    respx.get(f"{_AK_API}/core/users/").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"pk": 11, "username": "hex-provisioner", "is_superuser": False}]},
        )
    )
    respx.get(f"{_AK_API}/providers/oauth2/7/").mock(
        return_value=httpx.Response(200, json={"client_secret": "prov-secret"})
    )
    respx.post(f"{_AK_API}/core/tokens/").mock(return_value=httpx.Response(201, json={}))
    respx.get(f"{_AK_API}/core/tokens/{SA_TOKEN_IDENTIFIER}/view_key/").mock(
        return_value=httpx.Response(200, json={"key": "sa-key"})
    )


async def _set_phase(sessionmaker: async_sessionmaker[AsyncSession], phase: SetupPhase) -> None:
    async with sessionmaker() as session:
        state = await SetupStateManager(session).get_or_create()
        state.phase = phase
        await session.commit()


async def _audit_actions(sessionmaker: async_sessionmaker[AsyncSession]) -> list[str]:
    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id)))
            .scalars()
            .all()
        )
        return [row.action.value for row in rows]


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


async def test_setup_unlock_default_throttle_is_three(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The lowered default: three failures allowed, the fourth is throttled."""
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [
            (await client.post("/setup/unlock", json={"token": "x"})).status_code for _ in range(4)
        ]
    assert codes == [401, 401, 401, 429]


async def test_setup_unlock_audits_failures_and_throttle(
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
        for _ in range(3):
            await client.post("/setup/unlock", json={"token": "x"})

    assert await _audit_actions(sessionmaker) == [
        "setup.unlock.failed",
        "setup.unlock.failed",
        "setup.unlock.throttled",
    ]


async def test_setup_unlock_lockout_burns_token_and_freezes(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Sustained failures past the threshold burn the token and freeze the surface with 423."""
    app = create_app(make_settings(setup_unlock_max_attempts=100, setup_unlock_lockout_threshold=3))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        token = await SetupStateManager(session).issue_setup_token()
    assert token is not None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [
            (await client.post("/setup/unlock", json={"token": "x"})).status_code for _ in range(3)
        ]
        # Frozen now — even the real token is refused until a restart.
        after = await client.post("/setup/unlock", json={"token": token})

    assert codes == [401, 401, 423]
    assert after.status_code == 423
    assert await _audit_actions(sessionmaker) == [
        "setup.unlock.failed",
        "setup.unlock.failed",
        "setup.unlock.locked_out",
    ]
    async with sessionmaker() as session:
        state = await session.get(SetupState, 1)
        assert state is not None
        assert state.setup_token_hash is None  # burned
        assert state.phase is SetupPhase.FIRST_RUN  # locked, never advanced


async def test_setup_unlock_best_effort_audit_never_becomes_500(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed failure-audit write is swallowed: the client still gets 401, never a 500."""
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()

    async def boom_append(self: AuditLogManager, **kwargs: object) -> None:
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(AuditLogManager, "append", boom_append)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/setup/unlock", json={"token": "x"})
    assert resp.status_code == 401


async def _wire_app(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession], phase: SetupPhase
) -> AsyncClient:
    app = create_app(make_settings(authentik_base_url=_AK, authentik_bootstrap_token="boot-tok"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    await _set_phase(sessionmaker, phase)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_wire_succeeds_in_bootstrap_persists_and_audits(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _wire_app(engine, sessionmaker, SetupPhase.BOOTSTRAP)
    with respx.mock:
        _mock_authentik_happy()
        async with client:
            resp = await client.post("/setup/wire")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True, "client_id": "cid", "provider_pk": 7}

    async with sessionmaker() as session:
        row = await AuthentikIntegrationManager(session).get()
        assert row is not None and row.client_id == "cid" and row.wired_at is not None
        rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        audit_blob = " ".join(f"{r.action.value} {r.target} {r.meta}" for r in rows)
    actions = await _audit_actions(sessionmaker)
    assert "authentik.wiring.succeeded" in actions
    assert "bootstrap.token.rotated" in actions
    # No secret — the bootstrap token, read-back client secret, or SA key — leaks into the
    # response body or any audit row (non-negotiables #4/#9).
    for secret in ("boot-tok", "prov-secret", "sa-key"):
        assert secret not in resp.text
        assert secret not in audit_blob


async def test_wire_is_forbidden_before_bootstrap(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _wire_app(engine, sessionmaker, SetupPhase.FIRST_RUN)
    async with client:
        resp = await client.post("/setup/wire")
    assert resp.status_code == 409
    # Nothing was wired or audited from a wrong-phase call.
    async with sessionmaker() as session:
        assert await AuthentikIntegrationManager(session).get() is None
    assert await _audit_actions(sessionmaker) == []


async def test_wire_is_forbidden_after_complete(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _wire_app(engine, sessionmaker, SetupPhase.COMPLETE)
    async with client:
        resp = await client.post("/setup/wire")
    assert resp.status_code == 409


async def test_wire_unreachable_authentik_is_503_and_audits_failure(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _wire_app(engine, sessionmaker, SetupPhase.BOOTSTRAP)
    with respx.mock:
        respx.get(f"{_AK}/-/health/ready/").mock(return_value=httpx.Response(204))
        respx.get(f"{_AK_API}/core/applications/").mock(return_value=httpx.Response(503))
        async with client:
            resp = await client.post("/setup/wire")
    assert resp.status_code == 503
    # Fail-secure: nothing persisted, and the failure is a HIGH audit event.
    async with sessionmaker() as session:
        assert await AuthentikIntegrationManager(session).get() is None
    assert await _audit_actions(sessionmaker) == ["authentik.wiring.failed"]


async def test_wire_without_bootstrap_token_is_502_and_audits_failure(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # In BOOTSTRAP but misconfigured (no bootstrap token): a clean 502 + audited failure, not a 500.
    app = create_app(make_settings(authentik_base_url=_AK))  # no bootstrap token
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    await _set_phase(sessionmaker, SetupPhase.BOOTSTRAP)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/setup/wire")
    assert resp.status_code == 502
    async with sessionmaker() as session:
        assert await AuthentikIntegrationManager(session).get() is None
    assert await _audit_actions(sessionmaker) == ["authentik.wiring.failed"]


async def test_wire_persistence_failure_is_audited_and_persists_nothing(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Authentik failure in the persist tail is still audited (never an unaudited 500)."""

    async def boom_set_oidc(self: AuthentikIntegrationManager, **kwargs: object) -> None:
        # Flush a row first, THEN fail — so the test proves the failure handler's rollback
        # discards an already-flushed partial write, not just a pre-flush abort.
        await self.get_or_create()
        raise RuntimeError("db write failed")

    monkeypatch.setattr(AuthentikIntegrationManager, "set_oidc", boom_set_oidc)
    client = await _wire_app(engine, sessionmaker, SetupPhase.BOOTSTRAP)
    with respx.mock:
        _mock_authentik_happy()
        async with client:
            resp = await client.post("/setup/wire")
    assert resp.status_code == 500
    async with sessionmaker() as session:
        assert await AuthentikIntegrationManager(session).get() is None
    assert await _audit_actions(sessionmaker) == ["authentik.wiring.failed"]


async def test_setup_unlock_burn_db_error_is_503(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DB error while burning the token during lockout surfaces as 503, not a 500."""
    app = create_app(make_settings(setup_unlock_max_attempts=100, setup_unlock_lockout_threshold=1))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()

    async def boom_burn(
        self: SetupStateManager, audit: AuditLogManager, *, actor: str, failure_count: int
    ) -> None:
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(SetupStateManager, "burn_setup_token", boom_burn)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/setup/unlock", json={"token": "x"})
    assert resp.status_code == 503
