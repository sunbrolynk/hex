"""Invite routes: owner CRUD (require_owner), the public preview, and the capability abuse cases."""

import importlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.main import create_app
from hex.authentik.runtime_config import SACredentials
from hex.database import AuditLogManager, Invite, InviteManager, SessionManager, User
from hex.database.models import AuditLogEntry, SetupPhase, SetupState
from hex.secrets.errors import InvalidToken
from hex.setup import hash_token
from tests.conftest import make_settings

_AK = "http://ak.test"
# import_module returns the real submodule (plain `import …router` binds the re-exported APIRouter).
invite_router_mod = importlib.import_module("hex.api.invite_routes.router")


def _stub_sa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        invite_router_mod,
        "resolve_sa_credentials",
        lambda *a: SACredentials(api_base=_AK, browser_base=_AK, token="sa-tok"),
    )


def _mock_authentik(*, mint_status: int = 201) -> None:
    respx.get(f"{_AK}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": "flow-pk"}]})
    )
    respx.post(f"{_AK}/api/v3/stages/invitation/invitations/").mock(
        return_value=httpx.Response(mint_status, json={"pk": "itok-123"})
    )


async def _make_invite(client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]) -> str:
    await _auth(client, sessionmaker)
    return str((await client.post("/invites", json={})).json()["token"])


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(env="dev"))  # dev → non-Secure cookie round-trips over http://
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    phase: SetupPhase = SetupPhase.COMPLETE,
    is_owner: bool = True,
) -> str:
    """Seed setup-state + a (owner) user with a live session; return the raw session token."""
    async with sessionmaker() as session:
        session.add(SetupState(id=1, phase=phase))
        user = User(authentik_sub="u-sub", username="u", email="u@example.test", is_owner=is_owner)
        session.add(user)
        await session.flush()
        raw = await SessionManager(session, lifetime_seconds=3600).create(user)
        await session.commit()
        return raw


async def _audit_actions(sessionmaker: async_sessionmaker[AsyncSession]) -> list[str]:
    async with sessionmaker() as session:
        return list((await session.execute(select(AuditLogEntry.action))).scalars().all())


async def _auth(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    phase: SetupPhase = SetupPhase.COMPLETE,
    is_owner: bool = True,
) -> None:
    raw = await _seed(sessionmaker, phase=phase, is_owner=is_owner)
    client.cookies.set("hex_session", raw)


async def test_owner_creates_invite_returns_token_once_and_audits(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    resp = await client.post("/invites", json={"requestable": ["jellyfin"], "ttl_hours": 24})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token"] and "expires_at" in body
    # The token is stored only as a hash — never retrievable again.
    async with sessionmaker() as session:
        invite = (await session.execute(select(Invite))).scalar_one()
        assert invite.token_hash == hash_token(body["token"])
    assert "invite.created" in await _audit_actions(sessionmaker)


async def test_invite_created_audit_row_is_complete(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    created = (await client.post("/invites", json={})).json()
    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(AuditLogEntry).where(AuditLogEntry.action == "invite.created")
            )
        ).scalar_one()
    assert row.severity == "notice"
    assert row.result == "success"
    assert row.target == f"invite:{created['id']}"
    assert row.actor.startswith("user:")


async def test_create_rolls_back_when_audit_write_fails(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An unaudited capability must never exist (#7): an audit-write failure persists no invite.
    await _auth(client, sessionmaker)

    async def boom(self: AuditLogManager, **kwargs: object) -> None:
        raise OperationalError("INSERT audit", {}, Exception("audit down"))

    monkeypatch.setattr(AuditLogManager, "append", boom)
    assert (await client.post("/invites", json={})).status_code == 503
    async with sessionmaker() as session:
        count = (await session.execute(select(func.count()).select_from(Invite))).scalar_one()
    assert count == 0


async def test_create_requires_a_session(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # Setup complete (so the setup-gate passes), but no session cookie → 401 from require_user.
    async with sessionmaker() as session:
        session.add(SetupState(id=1, phase=SetupPhase.COMPLETE))
        await session.commit()
    assert (await client.post("/invites", json={})).status_code == 401


async def test_create_requires_owner(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker, is_owner=False)
    assert (await client.post("/invites", json={})).status_code == 403


async def test_create_forbidden_until_setup_complete(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker, phase=SetupPhase.FIRST_RUN)
    assert (await client.post("/invites", json={})).status_code == 403


async def test_list_and_revoke(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    created = (await client.post("/invites", json={"ttl_hours": 24})).json()

    listed = (await client.get("/invites")).json()
    assert [i["id"] for i in listed] == [created["id"]]
    assert listed[0]["status"] == "active"

    revoked = (await client.post(f"/invites/{created['id']}/revoke", json={})).json()
    assert revoked["status"] == "revoked"
    assert "invite.revoked" in await _audit_actions(sessionmaker)
    # Re-revoking a revoked invite is a 409.
    assert (await client.post(f"/invites/{created['id']}/revoke", json={})).status_code == 409


async def test_revoke_unknown_is_409(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    assert (await client.post("/invites/999/revoke", json={})).status_code == 409


async def test_preview_valid_invite(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    token = (
        await client.post(
            "/invites",
            json={"requestable": ["plex"], "default_grants": {"jellyfin": {"libraries": ["m"]}}},
        )
    ).json()["token"]
    preview = await client.get(f"/invite/{token}/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["requestable"] == ["plex"]
    assert body["grant_providers"] == ["jellyfin"]


async def test_preview_unknown_token_is_uniform_404(client: AsyncClient) -> None:
    assert (await client.get("/invite/not-a-real-token/preview")).status_code == 404


async def test_preview_revoked_invite_is_404(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    created = (await client.post("/invites", json={})).json()
    await client.post(f"/invites/{created['id']}/revoke", json={})
    assert (await client.get(f"/invite/{created['token']}/preview")).status_code == 404


async def test_preview_expired_invite_is_404(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # Insert an already-expired invite directly (TTL is bounded ≥1h via the API).
    raw = "expired-token-xyz"
    async with sessionmaker() as session:
        session.add(SetupState(id=1, phase=SetupPhase.COMPLETE))
        owner = User(authentik_sub="o", username="o", is_owner=True)
        session.add(owner)
        await session.flush()
        session.add(
            Invite(
                token_hash=hash_token(raw),
                created_by=owner.id,
                default_grants={},
                requestable=[],
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await session.commit()
    assert (await client.get(f"/invite/{raw}/preview")).status_code == 404


async def test_list_shows_accepted_and_expired_status(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    async with sessionmaker() as session:
        owner = (await session.execute(select(User).where(User.is_owner.is_(True)))).scalar_one()
        now = datetime.now(UTC)
        session.add(
            Invite(
                token_hash=hash_token("acc"),
                created_by=owner.id,
                default_grants={},
                requestable=[],
                expires_at=now + timedelta(hours=1),
                accepted_at=now,
            )
        )
        session.add(
            Invite(
                token_hash=hash_token("exp"),
                created_by=owner.id,
                default_grants={},
                requestable=[],
                expires_at=now - timedelta(hours=1),
            )
        )
        await session.commit()
    statuses = {i["status"] for i in (await client.get("/invites")).json()}
    assert {"accepted", "expired"} <= statuses


async def test_create_db_failure_is_503(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _auth(client, sessionmaker)

    async def boom(self: InviteManager, **kwargs: object) -> object:
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(InviteManager, "create", boom)
    assert (await client.post("/invites", json={})).status_code == 503


async def test_revoke_db_failure_is_503(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _auth(client, sessionmaker)
    created = (await client.post("/invites", json={})).json()

    async def boom(self: InviteManager, invite_id: int) -> object:
        raise OperationalError("UPDATE", {}, Exception("db down"))

    monkeypatch.setattr(InviteManager, "revoke", boom)
    assert (await client.post(f"/invites/{created['id']}/revoke", json={})).status_code == 503


@respx.mock
async def test_accept_burns_invite_and_returns_enroll_url(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await _make_invite(client, sessionmaker)
    _stub_sa(monkeypatch)
    _mock_authentik()

    resp = await client.post(f"/invite/{token}/accept")
    assert resp.status_code == 200
    assert resp.json()["enroll_url"] == f"{_AK}/if/flow/hex-enrollment/?itoken=itok-123"
    assert "invite.accepted" in await _audit_actions(sessionmaker)

    # The cookie carries a fresh server nonce — NOT the raw (now-burned) invite token — and its hash
    # is persisted for the 6-2c lookup.
    cookie = resp.cookies.get("hex_invite")
    assert cookie and cookie != token

    # The accepted-invite audit row is complete (actor/target/severity/result), not just present.
    async with sessionmaker() as session:
        stored = (await session.execute(select(Invite))).scalar_one()
        invite_id = stored.id
        assert stored.accept_nonce_hash == hash_token(cookie)
        row = (
            await session.execute(
                select(AuditLogEntry).where(AuditLogEntry.action == "invite.accepted")
            )
        ).scalar_one()
    assert row.severity == "notice"
    assert row.result == "success"
    assert row.target == f"invite:{invite_id}"
    assert row.actor.startswith("client:")

    # Single-use: the second accept of the same token is refused (atomic burn already happened).
    again = await client.post(f"/invite/{token}/accept")
    assert again.status_code == 404


@respx.mock
async def test_accept_uses_browser_base_for_redirect_and_api_base_for_calls(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Split-horizon: the Authentik API is called on the internal base; the user-facing enroll_url
    # uses the public base. A swap of the two must be caught here.
    token = await _make_invite(client, sessionmaker)
    api, pub = "http://int.test", "http://pub.test"
    monkeypatch.setattr(
        invite_router_mod,
        "resolve_sa_credentials",
        lambda *a: SACredentials(api_base=api, browser_base=pub, token="sa"),
    )
    respx.get(f"{api}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": "flow-pk"}]})
    )
    respx.post(f"{api}/api/v3/stages/invitation/invitations/").mock(
        return_value=httpx.Response(201, json={"pk": "itok-9"})
    )
    resp = await client.post(f"/invite/{token}/accept")
    assert resp.status_code == 200
    assert resp.json()["enroll_url"] == f"{pub}/if/flow/hex-enrollment/?itoken=itok-9"


async def test_accept_unknown_token_is_404(client: AsyncClient) -> None:
    assert (await client.post("/invite/not-a-real-token/accept")).status_code == 404


async def test_accept_expired_invite_is_404_and_not_spent(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # An expired-but-unaccepted invite: the atomic burn matches but the expiry check rolls it back.
    raw = "expired-accept-token"
    async with sessionmaker() as session:
        session.add(SetupState(id=1, phase=SetupPhase.COMPLETE))
        owner = User(authentik_sub="o", username="o", is_owner=True)
        session.add(owner)
        await session.flush()
        session.add(
            Invite(
                token_hash=hash_token(raw),
                created_by=owner.id,
                default_grants={},
                requestable=[],
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await session.commit()
    assert (await client.post(f"/invite/{raw}/accept")).status_code == 404
    async with sessionmaker() as session:
        invite = (await session.execute(select(Invite))).scalar_one()
    assert invite.accepted_at is None  # rolled back — not spent


async def test_accept_503_and_not_spent_when_not_wired(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # No Authentik integration row → resolve_sa_credentials returns None → 503, invite NOT spent.
    token = await _make_invite(client, sessionmaker)
    assert (await client.post(f"/invite/{token}/accept")).status_code == 503
    assert (await client.get(f"/invite/{token}/preview")).status_code == 200  # still acceptable


@respx.mock
async def test_accept_rolls_back_burn_when_mint_fails(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await _make_invite(client, sessionmaker)
    _stub_sa(monkeypatch)
    _mock_authentik(mint_status=500)  # Authentik invitation create fails

    assert (await client.post(f"/invite/{token}/accept")).status_code == 503
    # The HEx invite must NOT be spent if the Authentik invitation couldn't be minted.
    assert (await client.get(f"/invite/{token}/preview")).status_code == 200


async def test_accept_is_rate_limited(client: AsyncClient) -> None:
    for _ in range(10):
        assert (await client.post("/invite/bad/accept")).status_code == 404
    assert (await client.post("/invite/bad/accept")).status_code == 429


async def test_accept_503_on_undecryptable_sa_token(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await _make_invite(client, sessionmaker)

    def boom(*args: object) -> SACredentials:
        raise InvalidToken

    monkeypatch.setattr(invite_router_mod, "resolve_sa_credentials", boom)
    assert (await client.post(f"/invite/{token}/accept")).status_code == 503
    assert (await client.get(f"/invite/{token}/preview")).status_code == 200  # not spent


@respx.mock
async def test_accept_503_and_not_spent_when_audit_write_fails(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The audit append + commit share one try-block; a failure there rolls back the burn.
    token = await _make_invite(client, sessionmaker)
    _stub_sa(monkeypatch)
    _mock_authentik()

    async def boom(self: AuditLogManager, **kwargs: object) -> None:
        raise OperationalError("audit", {}, Exception("db down"))

    monkeypatch.setattr(AuditLogManager, "append", boom)
    assert (await client.post(f"/invite/{token}/accept")).status_code == 503
    assert (await client.get(f"/invite/{token}/preview")).status_code == 200  # rolled back


async def test_accept_is_single_use_at_manager_level(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Direct proof of the atomic burn: two accepts of the same token, one wins, one gets None.
    async with sessionmaker() as session:
        owner = User(authentik_sub="o", username="o", is_owner=True)
        session.add(owner)
        await session.flush()
        _, raw = await InviteManager(session).create(
            owner_id=owner.id, default_grants={}, requestable=[], ttl_seconds=3600
        )
        await session.commit()
    async with sessionmaker() as session:
        manager = InviteManager(session)
        first = await manager.accept(raw)
        second = await manager.accept(raw)
    assert first is not None
    assert second is None


async def test_preview_is_rate_limited(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # Default limiter is 10 failures / 60s; the 11th is throttled.
    for _ in range(10):
        assert (await client.get("/invite/bad/preview")).status_code == 404
    assert (await client.get("/invite/bad/preview")).status_code == 429


async def test_link_to_user_binds_first_wins_by_nonce(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # The shared bind for both 6-2d signals (signed claim + cookie): matched by the acceptance nonce
    # (only set on an accepted invite), first-wins so a replay can't re-bind.
    async with sessionmaker() as session:
        owner = User(authentik_sub="o", username="o", is_owner=True)
        session.add(owner)
        await session.flush()
        invite = Invite(
            token_hash=hash_token("a"),
            created_by=owner.id,
            default_grants={},
            requestable=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            accepted_at=datetime.now(UTC),
            accept_nonce_hash=hash_token("the-nonce"),
        )
        session.add(invite)
        await session.flush()
        manager = InviteManager(session)

        bound = await manager.link_to_user("the-nonce", 7)
        assert bound is not None and bound.accepted_by == 7
        assert await manager.link_to_user("the-nonce", 8) is None  # first-wins, no rebind
        assert await manager.link_to_user("wrong-nonce", 7) is None  # no match
