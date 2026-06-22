"""OIDC BFF auth routes: login redirect, callback validation, /me, logout — and abuse cases."""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.auth_routes.router import _safe_redirect
from hex.api.main import create_app
from hex.config import Settings
from hex.database import AuditLogManager, LoginStateManager, UserSession
from hex.database.models import AuditLogEntry, OIDCLoginState
from tests.conftest import make_settings
from tests.oidc import _oidc


def _settings(**overrides: object) -> Settings:
    return make_settings(
        authentik_base_url=_oidc.BASE,
        authentik_oidc_client_id=_oidc.CLIENT_ID,
        authentik_oidc_client_secret="client-secret",
        authentik_oidc_app_slug=_oidc.SLUG,
        **overrides,
    )


def _mock_oidc(*, id_token: str | None = None, token_status: int = 200) -> None:
    respx.get(_oidc.DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=_oidc.discovery_doc())
    )
    respx.get(_oidc.JWKS_URL).mock(return_value=httpx.Response(200, json=_oidc.jwks_dict()))
    body = {"id_token": id_token or _oidc.id_token(), "access_token": "a", "token_type": "Bearer"}
    respx.post(_oidc.TOKEN_URL).mock(return_value=httpx.Response(token_status, json=body))


async def _seed_state(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    state: str = "state-1",
    nonce: str = _oidc.NONCE,
    redirect_to: str = "/",
) -> None:
    async with sessionmaker() as session:
        await LoginStateManager(session, ttl_seconds=600).create(
            state=state, nonce=nonce, code_verifier="verifier", redirect_to=redirect_to
        )
        await session.commit()


async def _audit_actions(sessionmaker: async_sessionmaker[AsyncSession]) -> list[str]:
    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id)))
            .scalars()
            .all()
        )
        return [r.action.value for r in rows]


async def _session_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(UserSession)) or 0


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    # env=dev → non-Secure cookie, so it round-trips over the in-process http:// transport.
    app = create_app(_settings(env="dev"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_safe_redirect_blocks_open_redirects() -> None:
    assert _safe_redirect("/dashboard") == "/dashboard"
    assert _safe_redirect("https://evil.test") == "/"
    assert _safe_redirect("//evil.test") == "/"
    assert _safe_redirect("/\\evil.test") == "/"
    assert _safe_redirect(None) == "/"


@respx.mock
async def test_login_redirects_to_authentik(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    resp = await client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith(_oidc.AUTHORIZE_URL)
    params = parse_qs(urlparse(location).query)
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert "state" in params and "nonce" in params
    # The login-flow state row was persisted.
    async with sessionmaker() as session:
        from hex.database.models import OIDCLoginState

        assert await session.scalar(select(func.count()).select_from(OIDCLoginState)) == 1


async def test_login_unconfigured_returns_503(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    app = create_app(make_settings())  # no OIDC trio
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 503


@respx.mock
async def test_login_sanitizes_open_redirect_next(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    await client.get("/auth/login", params={"next": "https://evil.test"}, follow_redirects=False)
    async with sessionmaker() as session:
        from hex.database.models import OIDCLoginState

        row = (await session.execute(select(OIDCLoginState))).scalar_one()
    assert row.redirect_to == "/"  # external next rejected


@respx.mock
async def test_callback_happy_path_sets_cookie_and_audits(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    set_cookie = resp.headers["set-cookie"]
    assert "hex_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()  # dev (env != production)
    assert await _audit_actions(sessionmaker) == ["oidc.login.succeeded"]
    assert await _session_count(sessionmaker) == 1


@respx.mock
async def test_callback_cookie_is_secure_in_production(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    app = create_app(_settings(env="production"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    await _seed_state(sessionmaker, state="prod")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/auth/callback", params={"code": "c", "state": "prod"}, follow_redirects=False
        )
    assert "secure" in resp.headers["set-cookie"].lower()


@respx.mock
async def test_callback_replayed_state_fails(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "never-issued"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/?login=failed"
    assert await _audit_actions(sessionmaker) == ["oidc.login.failed"]
    assert await _session_count(sessionmaker) == 0


@respx.mock
async def test_callback_exchange_failure_is_clean(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc(token_status=400)
    await _seed_state(sessionmaker, state="good")
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302  # not a 500
    assert resp.headers["location"] == "/?login=failed"
    assert await _audit_actions(sessionmaker) == ["oidc.login.failed"]
    assert await _session_count(sessionmaker) == 0


@respx.mock
async def test_callback_bad_id_token_fails(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc(id_token=_oidc.id_token(aud="someone-else"))
    await _seed_state(sessionmaker, state="good")
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.headers["location"] == "/?login=failed"
    assert await _session_count(sessionmaker) == 0


@respx.mock
async def test_callback_fail_closed_when_audit_write_fails(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed success-audit write rolls the session back — no login without its record."""
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")

    async def boom(self: AuditLogManager, **kwargs: object) -> None:
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(AuditLogManager, "append", boom)
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302  # clean redirect, not 500
    assert await _session_count(sessionmaker) == 0  # session rolled back
    # The one-time state stays consumed — the rollback must NOT resurrect it (regression).
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(OIDCLoginState)) == 0


@respx.mock
async def test_login_discovery_failure_returns_503(client: AsyncClient) -> None:
    respx.get(_oidc.DISCOVERY_URL).mock(return_value=httpx.Response(503))
    resp = await client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 503


@respx.mock
async def test_callback_authentik_error_fails(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    resp = await client.get(
        "/auth/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert resp.headers["location"] == "/?login=failed"
    assert await _audit_actions(sessionmaker) == ["oidc.login.failed"]
    assert await _session_count(sessionmaker) == 0


async def test_logout_without_cookie_is_noop(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    resp = await client.post("/auth/logout")
    assert resp.status_code == 204
    assert await _audit_actions(sessionmaker) == []  # nothing to revoke, nothing audited


async def test_me_with_invalid_cookie_is_401(client: AsyncClient) -> None:
    client.cookies.set("hex_session", "not-a-real-token")
    assert (await client.get("/auth/me")).status_code == 401


async def test_logout_with_invalid_cookie_is_noop(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    client.cookies.set("hex_session", "not-a-real-token")
    resp = await client.post("/auth/logout")
    assert resp.status_code == 204
    assert await _audit_actions(sessionmaker) == []  # no session resolved → nothing audited


@respx.mock
async def test_me_and_logout_lifecycle(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # No session yet.
    assert (await client.get("/auth/me")).status_code == 401

    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"
    assert me.json()["is_owner"] is False

    logout = await client.post("/auth/logout")
    assert logout.status_code == 204
    # Server-side revocation is immediate: the same cookie no longer works.
    assert (await client.get("/auth/me")).status_code == 401
    assert "oidc.logout" in await _audit_actions(sessionmaker)
