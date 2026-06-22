"""UserManager: upsert from Authentik identity."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import UserManager
from hex.database.models import User


async def test_upsert_creates_then_refreshes(db_session: AsyncSession) -> None:
    manager = UserManager(db_session)
    first = await manager.upsert(authentik_sub="sub-1", username="alice", email="a@example.com")
    await db_session.commit()
    assert first.id is not None
    assert first.is_owner is False  # role is never set here (Slice 3)

    again = await manager.upsert(authentik_sub="sub-1", username="alice2", email="a2@example.com")
    await db_session.commit()
    assert again.id == first.id  # same user, keyed on authentik_sub
    assert again.username == "alice2"
    assert again.email == "a2@example.com"

    count = await db_session.scalar(select(func.count()).select_from(User))
    assert count == 1


async def test_upsert_distinct_subs_are_distinct_users(db_session: AsyncSession) -> None:
    manager = UserManager(db_session)
    a = await manager.upsert(authentik_sub="sub-a", username=None, email=None)
    b = await manager.upsert(authentik_sub="sub-b", username=None, email=None)
    await db_session.commit()
    assert a.id != b.id
