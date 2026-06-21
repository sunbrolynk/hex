"""SetupState model: singleton enforcement and enum persistence."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import SetupPhase, SetupState


async def test_singleton_check_rejects_second_row(db_session: AsyncSession) -> None:
    db_session.add(SetupState(id=1, phase=SetupPhase.FIRST_RUN))
    await db_session.commit()

    db_session.add(SetupState(id=2, phase=SetupPhase.FIRST_RUN))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_phase_round_trips_through_storage(db_session: AsyncSession) -> None:
    db_session.add(SetupState(id=1, phase=SetupPhase.BOOTSTRAP))
    await db_session.commit()
    db_session.expunge_all()  # force a real reload, not the identity-map copy

    fetched = await db_session.get(SetupState, 1)
    assert fetched is not None
    assert fetched.phase is SetupPhase.BOOTSTRAP
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
