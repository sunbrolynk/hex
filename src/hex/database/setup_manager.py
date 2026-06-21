"""Data access for the first-run setup-state singleton."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import SetupPhase, SetupState
from hex.setup import hash_token, mint_token, verify_token

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

    async def issue_setup_token(self) -> str | None:
        """Mint a fresh setup token while in FIRST_RUN, persist its hash, return the plaintext.

        Re-minting each boot invalidates any prior token (the plaintext is only ever logged, never
        stored). Returns None once setup has advanced past FIRST_RUN — no token, nothing to log.
        """
        state = await self.get_or_create()
        if state.phase is not SetupPhase.FIRST_RUN:
            return None
        token = mint_token()
        state.setup_token_hash = hash_token(token)
        state.setup_token_issued_at = datetime.now(UTC)
        await self._session.commit()
        return token

    async def begin_bootstrap(self, token: str) -> bool:
        """Constant-time verify the setup token; on success advance FIRST_RUN → BOOTSTRAP.

        Fail-secure: any of not-in-FIRST_RUN, no token issued, or mismatch returns False with no
        state change. On success the token is single-use (hash cleared) and ownership-claim is
        completion-bound — it can never be replayed.
        """
        state = await self.get_or_create()
        if state.phase is not SetupPhase.FIRST_RUN:
            verify_token(token, None)  # uniform timing whether or not we're still unlockable
            return False
        if not verify_token(token, state.setup_token_hash):
            return False
        # Atomic check-and-burn: the WHERE makes single-use a DB guarantee, not a read-then-write
        # race — only the request that flips FIRST_RUN wins (rowcount == 1), so two concurrent
        # valid-token unlocks can never both claim ownership.
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(SetupState)
                .where(SetupState.id == _SINGLETON_ID, SetupState.phase == SetupPhase.FIRST_RUN)
                .values(phase=SetupPhase.BOOTSTRAP, setup_token_hash=None)
            ),
        )
        await self._session.commit()
        return result.rowcount == 1
