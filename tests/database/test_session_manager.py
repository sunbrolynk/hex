"""SessionManager: server-side sessions, hashed at rest, immediate revocation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SessionManager, UserManager
from hex.database.models import UserSession
from hex.setup import hash_token


async def _user(session: AsyncSession, sub: str = "sub-1") -> int:
    user = await UserManager(session).upsert(authentik_sub=sub, username=None, email=None)
    await session.commit()
    return user.id


async def test_create_resolve_roundtrip(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).upsert(authentik_sub="s", username=None, email=None)
    await db_session.commit()
    manager = SessionManager(db_session, lifetime_seconds=3600)
    raw = await manager.create(user)
    await db_session.commit()

    resolved = await manager.resolve(raw)
    assert resolved is not None
    assert resolved.id == user.id


async def test_resolve_unknown_token_is_none(db_session: AsyncSession) -> None:
    assert await SessionManager(db_session, lifetime_seconds=3600).resolve("nope") is None


async def test_resolve_after_expiry_is_none(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).upsert(authentik_sub="s", username=None, email=None)
    await db_session.commit()
    manager = SessionManager(db_session, lifetime_seconds=-1)  # already expired
    raw = await manager.create(user)
    await db_session.commit()
    assert await manager.resolve(raw) is None


async def test_revoke_is_immediate(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).upsert(authentik_sub="s", username=None, email=None)
    await db_session.commit()
    manager = SessionManager(db_session, lifetime_seconds=3600)
    raw = await manager.create(user)
    await db_session.commit()
    assert await manager.resolve(raw) is not None

    await manager.revoke(raw)
    await db_session.commit()
    assert await manager.resolve(raw) is None  # stops working immediately, not at expiry


async def test_purge_expired_removes_only_expired(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).upsert(authentik_sub="s", username=None, email=None)
    await db_session.commit()
    await SessionManager(db_session, lifetime_seconds=-1).create(user)  # already expired
    live = await SessionManager(db_session, lifetime_seconds=3600).create(user)
    await db_session.commit()

    removed = await SessionManager(db_session, lifetime_seconds=3600).purge_expired()
    await db_session.commit()
    assert removed == 1
    # The live session still resolves.
    assert await SessionManager(db_session, lifetime_seconds=3600).resolve(live) is not None


async def test_token_is_hashed_at_rest(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).upsert(authentik_sub="s", username=None, email=None)
    await db_session.commit()
    raw = await SessionManager(db_session, lifetime_seconds=3600).create(user)
    await db_session.commit()

    rows = (await db_session.execute(select(UserSession))).scalars().all()
    assert len(rows) == 1
    assert rows[0].session_token_hash == hash_token(raw)
    assert rows[0].session_token_hash != raw  # raw token never persisted
