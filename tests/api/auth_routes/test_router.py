"""OIDC BFF auth routes: login redirect, callback validation, /me, logout — and abuse cases."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
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
from hex.database import (
    AuditLogManager,
    AuthentikIntegrationManager,
    Invite,
    LoginStateManager,
    User,
    UserSession,
)
from hex.database.models import AuditLogEntry, OIDCLoginState
from hex.setup import hash_token
from tests.conftest import make_settings
from tests.oidc import _oidc


async def _seed_accepted_invite(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    nonce: str,
    accepted_by: int | None = None,
) -> None:
    """An invite already burned in 6-2b, awaiting the 6-2c link via its acceptance nonce."""
    async with sessionmaker() as session:
        owner = User(authentik_sub="seed-owner", username="seed-owner", is_owner=True)
        session.add(owner)
        await session.flush()
        session.add(
            Invite(
                token_hash=hash_token(f"tok-{nonce}"),
                created_by=owner.id,
                default_grants={},
                requestable=[],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                accepted_at=datetime.now(UTC),
                accept_nonce_hash=hash_token(nonce),
                accepted_by=accepted_by,
            )
        )
        await session.commit()


async def _linked_invite_owner(sessionmaker: async_sessionmaker[AsyncSession]) -> int | None:
    async with sessionmaker() as session:
        return (await session.execute(select(Invite))).scalar_one().accepted_by


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
async def test_login_uses_db_wired_config_when_env_is_empty(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """The headline: with NO HEX_AUTHENTIK_* env, a bootstrap-wired DB row makes login work."""
    respx.get(_oidc.DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=_oidc.discovery_doc())
    )
    app = create_app(make_settings(env="dev"))  # env has no OIDC trio
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    broker = app.state.secrets
    async with sessionmaker() as session:
        await AuthentikIntegrationManager(session).set_oidc(
            base_url=_oidc.BASE,
            internal_base_url="",
            client_id=_oidc.CLIENT_ID,
            client_secret_enc=broker.encrypt("client-secret"),
            provider_pk=1,
            app_slug=_oidc.SLUG,
            sa_token_enc=broker.encrypt("sa-token"),
        )
        await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith(_oidc.AUTHORIZE_URL)


@respx.mock
async def test_login_fails_closed_when_db_secret_undecryptable(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """A persisted secret that won't decrypt (rotated/wrong KEK or tamper) → clean 503, not 500."""
    app = create_app(make_settings(env="dev"))
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with sessionmaker() as session:
        await AuthentikIntegrationManager(session).set_oidc(
            base_url=_oidc.BASE,
            internal_base_url="",
            client_id=_oidc.CLIENT_ID,
            client_secret_enc="not-a-decryptable-token",
            provider_pk=1,
            app_slug=_oidc.SLUG,
            sa_token_enc="x",
        )
        await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 503  # fail-secure: treated as unconfigured, no stack leak


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
async def test_callback_links_invite_via_nonce_cookie(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await _seed_accepted_invite(sessionmaker, nonce="nonce-123")
    client.cookies.set("hex_invite", "nonce-123")

    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302
    # The invite is bound to the freshly-created (non-owner) user, and the cookie is cleared.
    async with sessionmaker() as session:
        new_user = (
            await session.execute(select(User).where(User.is_owner.is_(False)))
        ).scalar_one()
    assert await _linked_invite_owner(sessionmaker) == new_user.id
    assert "invite.linked" in await _audit_actions(sessionmaker)  # privileged action audited (#7)
    cleared = [c for c in resp.headers.get_list("set-cookie") if c.startswith("hex_invite=")]
    assert cleared and "Max-Age=0" in cleared[0]


@respx.mock
async def test_callback_unknown_nonce_does_not_link_but_login_succeeds(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await _seed_accepted_invite(sessionmaker, nonce="real-nonce")
    client.cookies.set("hex_invite", "forged-nonce")  # no matching invite

    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302  # login still works
    assert await _linked_invite_owner(sessionmaker) is None  # nothing bound


@respx.mock
async def test_callback_empty_nonce_cookie_does_not_link(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # An empty cookie value must be treated as absent — no spurious bind, no clear-cookie emitted.
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await _seed_accepted_invite(sessionmaker, nonce="real-nonce")
    client.cookies.set("hex_invite", "")

    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert await _linked_invite_owner(sessionmaker) is None
    assert not [c for c in resp.headers.get_list("set-cookie") if c.startswith("hex_invite=")]


@respx.mock
async def test_callback_invite_bind_rolls_back_when_login_persist_fails(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The bind commits atomically with the login: if the login audit/commit fails, the invite must
    # NOT be left bound to a user whose session never persisted.
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await _seed_accepted_invite(sessionmaker, nonce="nonce-rb")
    client.cookies.set("hex_invite", "nonce-rb")

    async def boom(self: AuditLogManager, **kwargs: object) -> None:
        raise RuntimeError("audit backend down")

    monkeypatch.setattr(AuditLogManager, "append", boom)
    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302  # clean redirect, not 500
    assert await _session_count(sessionmaker) == 0  # session rolled back
    assert await _linked_invite_owner(sessionmaker) is None  # bind rolled back too


@respx.mock
async def test_callback_does_not_rebind_an_already_linked_invite(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _mock_oidc()
    await _seed_state(sessionmaker, state="good")
    await _seed_accepted_invite(sessionmaker, nonce="nonce-x", accepted_by=999)
    client.cookies.set("hex_invite", "nonce-x")

    resp = await client.get(
        "/auth/callback", params={"code": "c", "state": "good"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert await _linked_invite_owner(sessionmaker) == 999  # first-wins, not rebound


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
