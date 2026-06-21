"""SetupStateManager: singleton lifecycle + token-gated bootstrap entry."""

import secrets
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hex.audit import AuditSigner
from hex.database import AuditLogManager, SetupStateManager
from hex.database.models import (
    AuditAction,
    AuditLogEntry,
    AuditResult,
    AuditSeverity,
    SetupPhase,
    SetupState,
)
from hex.setup import hash_token


def _signer() -> AuditSigner:
    return AuditSigner(secrets.token_urlsafe(48).encode())


class _BoomSigner(AuditSigner):
    """A signer whose hash raises — used to prove a failed audit write rolls the action back."""

    def hash_entry(
        self,
        prev_hash: str,
        *,
        action: AuditAction,
        severity: AuditSeverity,
        result: AuditResult,
        actor: str,
        target: str | None,
        meta: dict[str, Any],
        occurred_at: datetime,
    ) -> str:
        raise RuntimeError("audit signer unavailable")


async def _actions(session: AsyncSession) -> list[AuditAction]:
    rows = (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id))).scalars().all()
    return [row.action for row in rows]


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


async def test_issue_setup_token_stores_only_the_hash(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash == hash_token(token)
    assert state.setup_token_hash != token  # plaintext is never persisted
    assert state.setup_token_issued_at is not None


async def test_issue_setup_token_remints_each_call(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    first = await manager.issue_setup_token()
    second = await manager.issue_setup_token()
    assert first != second  # a fresh boot invalidates the prior token


async def test_issue_setup_token_returns_none_past_first_run(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    state = await manager.get_or_create()
    state.phase = SetupPhase.BOOTSTRAP
    await db_session.commit()

    assert await manager.issue_setup_token() is None


async def test_begin_bootstrap_advances_on_correct_token(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None

    assert await manager.begin_bootstrap(token) is True
    assert await manager.current_phase() is SetupPhase.BOOTSTRAP

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash is None  # single-use: consumed on success


async def test_begin_bootstrap_rejects_wrong_token(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.issue_setup_token()

    assert await manager.begin_bootstrap("not-the-token") is False
    assert await manager.current_phase() is SetupPhase.FIRST_RUN  # no state change


async def test_begin_bootstrap_rejects_when_no_token_issued(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.get_or_create()  # FIRST_RUN but no token minted

    assert await manager.begin_bootstrap("anything") is False
    assert await manager.current_phase() is SetupPhase.FIRST_RUN


async def test_begin_bootstrap_is_completion_bound(db_session: AsyncSession) -> None:
    """Once setup has advanced, the token can never be replayed to re-claim ownership."""
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None
    assert await manager.begin_bootstrap(token) is True

    # A replay of the same token after advancing must not move the phase.
    assert await manager.begin_bootstrap(token) is False
    assert await manager.current_phase() is SetupPhase.BOOTSTRAP


async def test_begin_bootstrap_is_single_use_across_sessions(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Two valid-token unlocks (separate sessions) yield exactly one success — the atomic burn."""
    async with sessionmaker() as setup_session:
        token = await SetupStateManager(setup_session).issue_setup_token()
    assert token is not None

    async with sessionmaker() as s1, sessionmaker() as s2:
        first = await SetupStateManager(s1).begin_bootstrap(token)
        second = await SetupStateManager(s2).begin_bootstrap(token)
    assert sorted([first, second]) == [False, True]


async def test_issue_setup_token_audits_issuance(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    audit = AuditLogManager(db_session, _signer())
    token = await manager.issue_setup_token(audit)
    assert token is not None

    rows = (await db_session.execute(select(AuditLogEntry))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action is AuditAction.SETUP_TOKEN_ISSUED
    assert rows[0].severity is AuditSeverity.INFO
    assert rows[0].result is AuditResult.SUCCESS
    assert rows[0].actor == "system"


async def test_begin_bootstrap_audits_success_with_actor(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    audit = AuditLogManager(db_session, _signer())
    token = await manager.issue_setup_token(audit)
    assert token is not None

    assert await manager.begin_bootstrap(token, audit, actor="client:1.2.3.4") is True
    rows = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id))).scalars().all()
    )
    assert [r.action for r in rows] == [
        AuditAction.SETUP_TOKEN_ISSUED,
        AuditAction.SETUP_UNLOCK_SUCCEEDED,
    ]
    assert rows[1].actor == "client:1.2.3.4"
    assert rows[1].severity is AuditSeverity.NOTICE


async def test_burn_setup_token_freezes_and_audits_high(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    audit = AuditLogManager(db_session, _signer())
    await manager.issue_setup_token(audit)

    await manager.burn_setup_token(audit, actor="client:9.9.9.9", failure_count=10)

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash is None  # token burned
    assert state.phase is SetupPhase.FIRST_RUN  # still first run → locked, not advanced
    rows = (
        (await db_session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id))).scalars().all()
    )
    assert rows[-1].action is AuditAction.SETUP_UNLOCK_LOCKED_OUT
    assert rows[-1].severity is AuditSeverity.HIGH
    assert rows[-1].meta == {"failure_count": 10}


async def test_issue_setup_token_fail_closed_on_audit_error(db_session: AsyncSession) -> None:
    """A failed audit write rolls back the whole issuance — no token without its record."""
    manager = SetupStateManager(db_session)
    with pytest.raises(RuntimeError):
        await manager.issue_setup_token(AuditLogManager(db_session, _BoomSigner(b"k")))
    await db_session.rollback()

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash is None  # token not persisted
    count = await db_session.scalar(select(func.count()).select_from(AuditLogEntry))
    assert count == 0  # no audit row either


async def test_begin_bootstrap_fail_closed_on_audit_error(db_session: AsyncSession) -> None:
    """A failed success-audit write rolls back the phase advance and the token burn."""
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token(AuditLogManager(db_session, _signer()))
    assert token is not None

    with pytest.raises(RuntimeError):
        await manager.begin_bootstrap(token, AuditLogManager(db_session, _BoomSigner(b"k")))
    await db_session.rollback()

    assert await manager.current_phase() is SetupPhase.FIRST_RUN  # not advanced
    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash is not None  # not burned — rolled back
    assert await _actions(db_session) == [AuditAction.SETUP_TOKEN_ISSUED]  # only issuance survived
