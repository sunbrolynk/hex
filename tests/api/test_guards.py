"""forbid_until_setup_complete + require_owner: feature routes fail closed."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import require_owner
from hex.api.guards import forbid_until_setup_complete
from hex.database import SetupStateManager
from hex.database.models import SetupPhase, User


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


async def test_require_owner_allows_the_owner() -> None:
    owner = User(authentik_sub="s", username="o", email=None, is_owner=True)
    assert await require_owner(owner) is owner


async def test_require_owner_rejects_a_non_owner() -> None:
    user = User(authentik_sub="s", username="u", email=None, is_owner=False)
    with pytest.raises(HTTPException) as exc:
        await require_owner(user)
    assert exc.value.status_code == 403
