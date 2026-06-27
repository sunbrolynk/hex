"""Invite routes: owner CRUD (require_owner), the public preview, and the capability abuse cases."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hex.api.main import create_app
from hex.database import AuditLogManager, Invite, InviteManager, SessionManager, User
from hex.database.models import AuditLogEntry, SetupPhase, SetupState
from hex.setup import hash_token
from tests.conftest import make_settings


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
    preview = await client.get(f"/invite/{token}")
    assert preview.status_code == 200
    body = preview.json()
    assert body["requestable"] == ["plex"]
    assert body["grant_providers"] == ["jellyfin"]


async def test_preview_unknown_token_is_uniform_404(client: AsyncClient) -> None:
    assert (await client.get("/invite/not-a-real-token")).status_code == 404


async def test_preview_revoked_invite_is_404(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _auth(client, sessionmaker)
    created = (await client.post("/invites", json={})).json()
    await client.post(f"/invites/{created['id']}/revoke", json={})
    assert (await client.get(f"/invite/{created['token']}")).status_code == 404


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
    assert (await client.get(f"/invite/{raw}")).status_code == 404


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


async def test_preview_is_rate_limited(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    # Default limiter is 10 failures / 60s; the 11th is throttled.
    for _ in range(10):
        assert (await client.get("/invite/bad")).status_code == 404
    assert (await client.get("/invite/bad")).status_code == 429
