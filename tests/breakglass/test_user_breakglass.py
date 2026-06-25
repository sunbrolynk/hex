"""ensure_breakglass_owner: the single local owner identity, created idempotently."""

from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import UserManager


async def test_creates_local_owner_identity(db_session: AsyncSession) -> None:
    user = await UserManager(db_session).ensure_breakglass_owner("recovery-x")
    assert user.is_owner is True
    assert user.is_break_glass is True
    assert user.username == "recovery-x"


async def test_idempotent_reuses_the_single_row(db_session: AsyncSession) -> None:
    manager = UserManager(db_session)
    first = await manager.ensure_breakglass_owner("recovery-x")
    await db_session.flush()
    second = await manager.ensure_breakglass_owner("recovery-y")
    assert second.id == first.id  # one break-glass identity, not a new row each time
    assert second.username == "recovery-y"  # kept in sync with the configured username
