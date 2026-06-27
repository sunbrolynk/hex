"""POST /auth/breakglass: success, uniform failures, lockout, condition gate, validation."""

import base64
import secrets as pysecrets

import httpx
import pyotp
import pytest
import respx
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.auth_routes.dependencies import SESSION_COOKIE
from hex.api.guards import require_breakglass_listener
from hex.api.main import create_app
from hex.config import Settings
from hex.database import AuditLogManager, SessionManager, SetupStateManager
from hex.database.models import AuditAction, AuditLogEntry, User

_PASSPHRASE = "emergency-recovery-passphrase"
_USERNAME = "owner-recovery-7x"
_TOTP_SECRET = pyotp.random_base32()
_HASH = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1).hash(_PASSPHRASE)
_IDP_BASE = "http://authentik:9000"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "secret_key": pysecrets.token_urlsafe(64),
        "kek": base64.b64encode(pysecrets.token_bytes(32)).decode(),
        "audit_key": pysecrets.token_urlsafe(48),
        "db_password": pysecrets.token_urlsafe(32),
        "proxy_shared_secret": pysecrets.token_urlsafe(48),
        "db_auto_migrate": False,
        "breakglass_enabled": True,
        "breakglass_username": _USERNAME,
        "breakglass_password_hash": _HASH,
        "breakglass_totp_secret": _TOTP_SECRET,
        "breakglass_max_attempts": 3,
    }
    return Settings.model_validate(base | overrides)


def _code() -> str:
    return pyotp.TOTP(_TOTP_SECRET).now()


def _good_body() -> dict[str, str]:
    return {"username": _USERNAME, "password": _PASSPHRASE, "totp": _code()}


async def _make_client(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> AsyncClient:
    """An in-process client whose app has the test DB attached and the listener guard bypassed.

    The guard itself is covered in tests/api/test_breakglass_listener.py; here we exercise the
    authentication logic that sits behind it.
    """
    app = create_app(settings)
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.dependency_overrides[require_breakglass_listener] = lambda: None
    async with sessionmaker() as session:
        await SetupStateManager(session).get_or_create()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _actions(db_session: AsyncSession) -> list[AuditAction]:
    return list((await db_session.execute(select(AuditLogEntry.action))).scalars().all())


async def test_availability_probe_returns_ok_on_listener(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.get("/auth/breakglass")
    assert resp.status_code == 200
    assert resp.json() == {"available": True}


async def test_success_mints_owner_session(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post("/auth/breakglass", json=_good_body())
    assert resp.status_code == 200
    assert resp.json()["is_owner"] is True
    assert SESSION_COOKIE in resp.headers.get("set-cookie", "")

    user = (
        await db_session.execute(select(User).where(User.is_break_glass.is_(True)))
    ).scalar_one()
    assert user.username == _USERNAME
    assert AuditAction.BREAKGLASS_SUCCEEDED in await _actions(db_session)


async def test_wrong_password_is_generic_401(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post(
            "/auth/breakglass", json={"username": _USERNAME, "password": "nope", "totp": _code()}
        )
    assert resp.status_code == 401
    assert SESSION_COOKIE not in resp.headers.get("set-cookie", "")
    assert AuditAction.BREAKGLASS_FAILED in await _actions(db_session)


async def test_wrong_username_is_generic_401(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post(
            "/auth/breakglass",
            json={"username": "someone-else", "password": _PASSPHRASE, "totp": _code()},
        )
    assert resp.status_code == 401


async def test_wrong_totp_is_generic_401(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post(
            "/auth/breakglass",
            json={"username": _USERNAME, "password": _PASSPHRASE, "totp": "000000"},
        )
    assert resp.status_code == 401


async def test_lockout_after_repeated_failures(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())  # max_attempts=3
    async with client:
        for _ in range(3):
            bad = await client.post(
                "/auth/breakglass",
                json={"username": _USERNAME, "password": "nope", "totp": _code()},
            )
            assert bad.status_code == 401
        # Locked now: even a correct credential is refused with 429.
        locked = await client.post("/auth/breakglass", json=_good_body())
    assert locked.status_code == 429
    assert AuditAction.BREAKGLASS_LOCKED_OUT in await _actions(db_session)


@respx.mock
async def test_403_and_no_lockout_when_authentik_reachable(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    respx.get(f"{_IDP_BASE}/-/health/ready/").mock(return_value=httpx.Response(200))
    client = await _make_client(engine, sessionmaker, _settings(authentik_base_url=_IDP_BASE))
    async with client:
        # Correct credentials, but a healthy IdP closes the path.
        denied = await client.post("/auth/breakglass", json=_good_body())
        assert denied.status_code == 403
        # That denial must not count toward lockout: with the IdP now down, the same creds work.
        respx.get(f"{_IDP_BASE}/-/health/ready/").mock(return_value=httpx.Response(503))
        ok = await client.post("/auth/breakglass", json=_good_body())
    assert ok.status_code == 200


async def test_unknown_fields_rejected(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post(
            "/auth/breakglass",
            json={"username": _USERNAME, "password": _PASSPHRASE, "totp": _code(), "x": 1},
        )
    assert resp.status_code == 422


async def test_db_failure_on_success_fails_secure_503(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If persisting the session/audit fails, no cookie is granted — fail-secure (non-negotiable #6).
    async def boom(self: SessionManager, user: User) -> str:
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(SessionManager, "create", boom)
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post("/auth/breakglass", json=_good_body())
    assert resp.status_code == 503
    assert SESSION_COOKIE not in resp.headers.get("set-cookie", "")


async def test_audit_write_failure_does_not_500(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A failing audit write on the failure path must not turn a 401 into a 500.
    async def boom(self: AuditLogManager, **kwargs: object) -> None:
        raise RuntimeError("audit down")

    monkeypatch.setattr(AuditLogManager, "append", boom)
    client = await _make_client(engine, sessionmaker, _settings())
    async with client:
        resp = await client.post(
            "/auth/breakglass", json={"username": _USERNAME, "password": "nope", "totp": _code()}
        )
    assert resp.status_code == 401


async def test_route_guarded_404_when_breakglass_disabled(client: AsyncClient) -> None:
    # Without the guard override, the default (disabled) app 404s the POST — the boundary holds.
    resp = await client.post("/auth/breakglass", json=_good_body())
    assert resp.status_code == 404


async def test_availability_probe_404_off_listener(client: AsyncClient) -> None:
    # The GET probe 404s on the proxy origin too, so the UI reads as non-existent off-listener.
    resp = await client.get("/auth/breakglass")
    assert resp.status_code == 404
