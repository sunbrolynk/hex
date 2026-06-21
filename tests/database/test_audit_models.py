"""Audit-log model constraints + storage round-trip."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hex.database.models import (
    AuditAction,
    AuditChainHead,
    AuditLogEntry,
    AuditResult,
    AuditSeverity,
)


def _entry(**overrides: object) -> AuditLogEntry:
    base: dict[str, object] = {
        "occurred_at": datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC),
        "action": AuditAction.SETUP_TOKEN_ISSUED,
        "severity": AuditSeverity.INFO,
        "result": AuditResult.SUCCESS,
        "actor": "system",
        "target": "setup_state:1",
        "meta": {"k": "v"},
        "prev_hash": "0" * 64,
        "entry_hash": "a" * 64,
    }
    return AuditLogEntry(**(base | overrides))


async def test_chain_head_singleton_rejects_second_row(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        session.add(AuditChainHead(id=2, last_hash="0" * 64, seq=0))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_entry_hash_is_unique(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        session.add(_entry(entry_hash="dup" + "0" * 61))
        session.add(_entry(prev_hash="b" * 64, entry_hash="dup" + "0" * 61))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_enum_and_meta_round_trip(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        session.add(
            _entry(
                action=AuditAction.SETUP_UNLOCK_LOCKED_OUT,
                severity=AuditSeverity.HIGH,
                result=AuditResult.FAILURE,
                meta={"failure_count": 10, "client": "10.0.0.1"},
            )
        )
        await session.commit()
        session.expunge_all()

    async with sessionmaker() as session:
        loaded = await session.get(AuditLogEntry, 1)
        assert loaded is not None
        assert loaded.action is AuditAction.SETUP_UNLOCK_LOCKED_OUT
        assert loaded.severity is AuditSeverity.HIGH
        assert loaded.result is AuditResult.FAILURE
        assert loaded.meta == {"failure_count": 10, "client": "10.0.0.1"}
