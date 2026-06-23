"""Data access for the first-run setup-state singleton."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.audit_manager import AuditLogManager
from hex.database.models import (
    AuditAction,
    AuditResult,
    AuditSeverity,
    SetupPhase,
    SetupState,
    User,
)
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

    async def issue_setup_token(self, audit: AuditLogManager | None = None) -> str | None:
        """Mint a fresh setup token while in FIRST_RUN, persist its hash, return the plaintext.

        Re-minting each boot invalidates any prior token (the plaintext is only ever logged, never
        stored). Returns None once setup has advanced past FIRST_RUN — no token, nothing to log.
        The issuance audit row (when ``audit`` is given) commits in this same transaction, so a
        failed audit write rolls the token back — never a token without its record.
        """
        state = await self.get_or_create()
        if state.phase is not SetupPhase.FIRST_RUN:
            return None
        token = mint_token()
        state.setup_token_hash = hash_token(token)
        state.setup_token_issued_at = datetime.now(UTC)
        if audit is not None:
            await audit.append(
                action=AuditAction.SETUP_TOKEN_ISSUED,
                severity=AuditSeverity.INFO,
                result=AuditResult.SUCCESS,
                actor="system",
                target=f"setup_state:{_SINGLETON_ID}",
            )
        await self._session.commit()
        return token

    async def begin_bootstrap(
        self, token: str, audit: AuditLogManager | None = None, actor: str = "system"
    ) -> str | None:
        """Verify the setup token; on success advance FIRST_RUN → BOOTSTRAP and mint a session.

        Returns the bootstrap-session plaintext (to set as the ``hex_bootstrap`` cookie, proving the
        caller unlocked) on success, or None on any failure. Fail-secure: not-in-FIRST_RUN, no token
        issued, or mismatch all return None with no state change. The setup token is single-use
        (hash cleared) and completion-bound. The success audit row (when ``audit`` is given) commits
        in the same transaction as the burn — atomic.
        """
        state = await self.get_or_create()
        if state.phase is not SetupPhase.FIRST_RUN:
            verify_token(token, None)  # uniform timing whether or not we're still unlockable
            return None
        if not verify_token(token, state.setup_token_hash):
            return None
        session_token = mint_token()
        # Atomic check-and-burn: the WHERE makes single-use a DB guarantee, not a read-then-write
        # race — only the request that flips FIRST_RUN wins (rowcount == 1), so two concurrent
        # valid-token unlocks can never both claim ownership.
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(SetupState)
                .where(SetupState.id == _SINGLETON_ID, SetupState.phase == SetupPhase.FIRST_RUN)
                .values(
                    phase=SetupPhase.BOOTSTRAP,
                    setup_token_hash=None,
                    bootstrap_session_hash=hash_token(session_token),
                )
            ),
        )
        won = result.rowcount == 1
        if won and audit is not None:
            await audit.append(
                action=AuditAction.SETUP_UNLOCK_SUCCEEDED,
                severity=AuditSeverity.NOTICE,
                result=AuditResult.SUCCESS,
                actor=actor,
                target=f"setup_state:{_SINGLETON_ID}",
            )
        await self._session.commit()
        return session_token if won else None

    async def verify_bootstrap_session(self, token: str | None) -> bool:
        """Constant-time check of the bootstrap-session cookie against the stored hash.

        Fail-secure: a missing cookie or absent/mismatched hash returns False, with a decoy compare
        so timing never reveals whether a session is on file.
        """
        state = await self._session.get(SetupState, _SINGLETON_ID)
        stored = state.bootstrap_session_hash if state is not None else None
        if not token:
            verify_token("", stored)  # uniform timing
            return False
        return verify_token(token, stored)

    async def complete_setup(
        self, user_id: int, audit: AuditLogManager | None = None, actor: str = "system"
    ) -> bool:
        """Claim ownership: BOOTSTRAP → COMPLETE, mark the user owner, clear the bootstrap session.

        Single-use and atomic: only the request that flips BOOTSTRAP wins (rowcount == 1), so two
        concurrent claims can't both create an owner. Fail-secure: not-in-BOOTSTRAP returns False
        with no change. The ownership flip + the user update + the audit row commit together.
        """
        state = await self.get_or_create()
        if state.phase is not SetupPhase.BOOTSTRAP:
            return False
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(SetupState)
                .where(SetupState.id == _SINGLETON_ID, SetupState.phase == SetupPhase.BOOTSTRAP)
                .values(phase=SetupPhase.COMPLETE, bootstrap_session_hash=None)
            ),
        )
        if result.rowcount != 1:
            return False
        user_result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(User).where(User.id == user_id).values(is_owner=True)
            ),
        )
        if user_result.rowcount != 1:
            # No such user — never complete with no owner. The uncommitted phase flip rolls back.
            return False
        if audit is not None:
            await audit.append(
                action=AuditAction.OWNER_CLAIMED,
                severity=AuditSeverity.HIGH,
                result=AuditResult.SUCCESS,
                actor=actor,
                target=f"user:{user_id}",
            )
        await self._session.commit()
        return True

    async def burn_setup_token(
        self, audit: AuditLogManager, *, actor: str, failure_count: int
    ) -> None:
        """Lockout: clear the token hash so the install hard-freezes, and audit it (high severity).

        Phase stays FIRST_RUN with a null hash — the "locked" state. Idempotent. Recovery is a HEx
        restart, which re-mints (docs/BOOTSTRAP.md). The burn and its audit row commit atomically.
        """
        await self._session.execute(
            update(SetupState)
            .where(SetupState.id == _SINGLETON_ID, SetupState.phase == SetupPhase.FIRST_RUN)
            .values(setup_token_hash=None)
        )
        await audit.append(
            action=AuditAction.SETUP_UNLOCK_LOCKED_OUT,
            severity=AuditSeverity.HIGH,
            result=AuditResult.FAILURE,
            actor=actor,
            target=f"setup_state:{_SINGLETON_ID}",
            meta={"failure_count": failure_count},
        )
        await self._session.commit()
