"""LoginStateManager: one-time, expiring, hashed-at-rest login-flow state."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import LoginStateManager
from hex.database.models import OIDCLoginState
from hex.setup import hash_token


async def test_create_consume_roundtrip(db_session: AsyncSession) -> None:
    manager = LoginStateManager(db_session, ttl_seconds=600)
    await manager.create(state="st", nonce="no", code_verifier="ver", redirect_to="/x")
    await db_session.commit()

    flow = await manager.consume("st")
    assert flow is not None
    assert flow.nonce == "no"
    assert flow.code_verifier == "ver"
    assert flow.redirect_to == "/x"


async def test_consume_is_one_time(db_session: AsyncSession) -> None:
    manager = LoginStateManager(db_session, ttl_seconds=600)
    await manager.create(state="st", nonce="no", code_verifier="ver", redirect_to="/")
    await db_session.commit()

    assert await manager.consume("st") is not None
    await db_session.commit()
    assert await manager.consume("st") is None  # replayed state is rejected


async def test_consume_expired_is_none(db_session: AsyncSession) -> None:
    manager = LoginStateManager(db_session, ttl_seconds=-1)  # already expired
    await manager.create(state="st", nonce="no", code_verifier="ver", redirect_to="/")
    await db_session.commit()
    assert await manager.consume("st") is None


async def test_consume_unknown_is_none(db_session: AsyncSession) -> None:
    assert await LoginStateManager(db_session, ttl_seconds=600).consume("nope") is None


async def test_state_is_hashed_at_rest(db_session: AsyncSession) -> None:
    manager = LoginStateManager(db_session, ttl_seconds=600)
    await manager.create(state="raw-state", nonce="no", code_verifier="ver", redirect_to="/")
    await db_session.commit()
    rows = (await db_session.execute(select(OIDCLoginState))).scalars().all()
    assert len(rows) == 1
    assert rows[0].state_hash == hash_token("raw-state")
    assert rows[0].state_hash != "raw-state"
