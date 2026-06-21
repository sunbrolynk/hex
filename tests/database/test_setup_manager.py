"""SetupStateManager: singleton lifecycle."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SetupStateManager
from hex.database.models import SetupPhase, SetupState


async def test_get_or_create_is_idempotent(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)

    first = await manager.get_or_create()
    assert first.id == 1
    assert first.phase is SetupPhase.FIRST_RUN

    again = await manager.get_or_create()
    assert again.id == 1

    count = await db_session.scalar(select(func.count()).select_from(SetupState))
    assert count == 1


async def test_current_phase_defaults_first_run_before_init(db_session: AsyncSession) -> None:
    assert await SetupStateManager(db_session).current_phase() is SetupPhase.FIRST_RUN


async def test_is_first_run_until_complete(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.get_or_create()
    assert await manager.is_first_run() is True

    state = await db_session.get(SetupState, 1)
    assert state is not None
    state.phase = SetupPhase.COMPLETE
    await db_session.commit()

    assert await manager.is_first_run() is False
