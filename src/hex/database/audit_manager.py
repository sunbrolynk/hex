"""Append-only, tamper-evident audit log (non-negotiable #7).

Every privileged action is chained into a keyed HMAC hash chain so any edit, deletion, reorder,
or truncation is detectable by ``verify_chain``. The manager exposes only append + verify — no
update or delete path. ``append`` never commits: the caller owns the transaction, so a
state-changing action and its audit row commit (or roll back) atomically.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.audit.signer import GENESIS_HASH, AuditSigner
from hex.database.models import (
    AuditAction,
    AuditChainHead,
    AuditLogEntry,
    AuditResult,
    AuditSeverity,
)

_HEAD_ID = 1


class AuditLogManager:
    """Appends hash-chained entries and verifies chain integrity."""

    def __init__(self, session: AsyncSession, signer: AuditSigner) -> None:
        self._session = session
        self._signer = signer

    async def append(
        self,
        *,
        action: AuditAction,
        severity: AuditSeverity,
        result: AuditResult,
        actor: str,
        target: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        """Append one entry chained to the prior. Does NOT commit — the caller owns the txn.

        Locks the chain-head row (``FOR UPDATE``) so concurrent appends serialize and the chain
        cannot fork; the ``entry_hash`` UNIQUE index is the cross-dialect backstop.
        """
        head = await self._session.get(AuditChainHead, _HEAD_ID, with_for_update=True)
        if head is None:
            head = AuditChainHead(id=_HEAD_ID, last_hash=GENESIS_HASH, seq=0)
            self._session.add(head)
        entry_meta = meta or {}
        occurred_at = datetime.now(UTC)
        entry_hash = self._signer.hash_entry(
            head.last_hash,
            action=action,
            severity=severity,
            result=result,
            actor=actor,
            target=target,
            meta=entry_meta,
            occurred_at=occurred_at,
        )
        entry = AuditLogEntry(
            occurred_at=occurred_at,
            action=action,
            severity=severity,
            result=result,
            actor=actor,
            target=target,
            meta=entry_meta,
            prev_hash=head.last_hash,
            entry_hash=entry_hash,
        )
        self._session.add(entry)
        head.last_hash = entry_hash
        head.seq += 1
        return entry

    async def verify_chain(self) -> bool:
        """Recompute the chain from genesis; False on any edit, delete, reorder, or truncation."""
        entries = (
            (await self._session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id)))
            .scalars()
            .all()
        )
        prev = GENESIS_HASH
        for entry in entries:
            if entry.prev_hash != prev:
                return False
            if not self._signer.verify_entry(
                prev,
                entry.entry_hash,
                action=entry.action,
                severity=entry.severity,
                result=entry.result,
                actor=entry.actor,
                target=entry.target,
                meta=entry.meta,
                occurred_at=entry.occurred_at,
            ):
                return False
            prev = entry.entry_hash
        head = await self._session.get(AuditChainHead, _HEAD_ID)
        if head is None:
            return len(entries) == 0
        return head.last_hash == prev and head.seq == len(entries)
