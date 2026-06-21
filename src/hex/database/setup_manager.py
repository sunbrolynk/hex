"""Data access for the first-run setup-state singleton."""

from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import SetupPhase, SetupState

_SINGLETON_ID = 1


class SetupStateManager:
    """Read and advance the singleton setup-state row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self) -> SetupState:
        """Return the singleton row, creating it as FIRST_RUN if absent.

        Called once at startup (serial); the row's PK + singleton CHECK make a racing second
        creator fail secure rather than duplicate. Idempotent on repeat calls.
        """
        state = await self._session.get(SetupState, _SINGLETON_ID)
        if state is None:
            state = SetupState(id=_SINGLETON_ID, phase=SetupPhase.FIRST_RUN)
            self._session.add(state)
            await self._session.commit()
            await self._session.refresh(state)
        return state

    async def current_phase(self) -> SetupPhase:
        """Phase of this install (FIRST_RUN if not yet initialized)."""
        state = await self._session.get(SetupState, _SINGLETON_ID)
        return state.phase if state is not None else SetupPhase.FIRST_RUN

    async def is_first_run(self) -> bool:
        """True until setup completes."""
        return await self.current_phase() != SetupPhase.COMPLETE
