"""Audit-log manager tests: hash-chain integrity and tamper detection."""

import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hex.audit import GENESIS_HASH, AuditSigner
from hex.database import AuditLogManager
from hex.database.models import AuditAction, AuditChainHead, AuditResult, AuditSeverity


def _signer() -> AuditSigner:
    return AuditSigner(secrets.token_urlsafe(48).encode())


async def _append(
    sessionmaker: async_sessionmaker[AsyncSession], signer: AuditSigner, n: int
) -> None:
    async with sessionmaker() as session:
        manager = AuditLogManager(session, signer)
        for i in range(n):
            await manager.append(
                action=AuditAction.SETUP_TOKEN_ISSUED,
                severity=AuditSeverity.INFO,
                result=AuditResult.SUCCESS,
                actor=f"system:{i}",
            )
        await session.commit()


async def _verify(sessionmaker: async_sessionmaker[AsyncSession], signer: AuditSigner) -> bool:
    async with sessionmaker() as session:
        return await AuditLogManager(session, signer).verify_chain()


async def test_first_append_links_genesis_and_advances_head(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    signer = _signer()
    async with sessionmaker() as session:
        entry = await AuditLogManager(session, signer).append(
            action=AuditAction.SETUP_TOKEN_ISSUED,
            severity=AuditSeverity.INFO,
            result=AuditResult.SUCCESS,
            actor="system",
        )
        await session.commit()
        assert entry.prev_hash == GENESIS_HASH
        head = await session.get(AuditChainHead, 1)
        assert head is not None
        assert head.last_hash == entry.entry_hash
        assert head.seq == 1


async def test_clean_chain_verifies(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    signer = _signer()
    await _append(sessionmaker, signer, 3)
    assert await _verify(sessionmaker, signer) is True


async def test_empty_chain_verifies(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    assert await _verify(sessionmaker, _signer()) is True


async def test_detects_mutated_field(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    signer = _signer()
    await _append(sessionmaker, signer, 3)
    async with sessionmaker() as session:
        await session.execute(text("UPDATE audit_log SET actor='attacker' WHERE id=1"))
        await session.commit()
    assert await _verify(sessionmaker, signer) is False


async def test_detects_deleted_middle_row(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    signer = _signer()
    await _append(sessionmaker, signer, 3)
    async with sessionmaker() as session:
        await session.execute(text("DELETE FROM audit_log WHERE id=2"))
        await session.commit()
    assert await _verify(sessionmaker, signer) is False


async def test_detects_truncated_tail(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    signer = _signer()
    await _append(sessionmaker, signer, 3)
    async with sessionmaker() as session:
        # Drop the last row but leave the head pointing past it.
        await session.execute(text("DELETE FROM audit_log WHERE id=3"))
        await session.commit()
    assert await _verify(sessionmaker, signer) is False


async def test_detects_tampered_chain_head(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Rolling the head back (stale last_hash / seq) is caught even though every entry verifies."""
    signer = _signer()
    await _append(sessionmaker, signer, 3)
    async with sessionmaker() as session:
        await session.execute(text("UPDATE audit_chain_head SET seq = 2 WHERE id = 1"))
        await session.commit()
    assert await _verify(sessionmaker, signer) is False


async def test_detects_rekeyed_signer(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    await _append(sessionmaker, _signer(), 2)
    # A different key cannot reproduce the stored hashes.
    assert await _verify(sessionmaker, _signer()) is False


async def test_cross_session_appends_do_not_fork(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    signer = _signer()
    async with sessionmaker() as s1:
        await AuditLogManager(s1, signer).append(
            action=AuditAction.SETUP_TOKEN_ISSUED,
            severity=AuditSeverity.INFO,
            result=AuditResult.SUCCESS,
            actor="a",
        )
        await s1.commit()
    async with sessionmaker() as s2:
        await AuditLogManager(s2, signer).append(
            action=AuditAction.SETUP_UNLOCK_SUCCEEDED,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.SUCCESS,
            actor="b",
        )
        await s2.commit()
    async with sessionmaker() as session:
        manager = AuditLogManager(session, signer)
        assert await manager.verify_chain() is True
        head = await session.get(AuditChainHead, 1)
        assert head is not None
        assert head.seq == 2


def test_manager_is_append_only() -> None:
    """No update/delete surface — append-only is enforced in code, not just convention."""
    public = {name for name in dir(AuditLogManager) if not name.startswith("_")}
    assert public == {"append", "verify_chain"}
