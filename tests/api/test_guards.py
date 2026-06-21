"""forbid_until_setup_complete: feature routes fail closed during setup."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.guards import forbid_until_setup_complete
from hex.database import SetupStateManager
from hex.database.models import SetupPhase


async def _set_phase(session: AsyncSession, phase: SetupPhase) -> None:
    state = await SetupStateManager(session).get_or_create()
    state.phase = phase
    await session.commit()


@pytest.mark.parametrize("phase", [SetupPhase.FIRST_RUN, SetupPhase.BOOTSTRAP])
async def test_forbids_until_complete(db_session: AsyncSession, phase: SetupPhase) -> None:
    await _set_phase(db_session, phase)
    with pytest.raises(HTTPException) as exc:
        await forbid_until_setup_complete(db_session)
    assert exc.value.status_code == 403


async def test_allows_once_complete(db_session: AsyncSession) -> None:
    await _set_phase(db_session, SetupPhase.COMPLETE)
    await forbid_until_setup_complete(db_session)  # does not raise
