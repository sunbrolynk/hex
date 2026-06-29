"""The provisioning ledger — the backbone of offboarding, status, and recovery.

An append-leaning event log: each provision/deprovision/reconcile is a new ``ProvisioningEvent``,
never an overwrite. The *current* state of a ``(user, provider)`` grant is the latest event for that
pair (derived by query, no mutable projection). Returns the contract's ``LedgerEntry`` value objects
so providers stay decoupled from the DB. Audit-log wiring + orchestration land with the lifecycle
engine (Phase 3); this slice is storage + projection only.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import ProvisioningEvent
from hex.providers.types import LedgerEntry, ProvisionState

# States that still represent live or in-flight access — the set reconciliation walks.
_ACTIVE_STATES = frozenset(
    {
        ProvisionState.GRANTED,
        ProvisionState.PENDING_MANUAL,
        ProvisionState.PENDING_EXTERNAL_CLAIM,
        ProvisionState.PARTIAL,
    }
)


def _to_entry(row: ProvisioningEvent) -> LedgerEntry:
    return LedgerEntry(
        user_id=row.user_id,
        provider_id=row.provider_id,
        state=row.state,
        external_ref=row.external_ref,
        grant=row.grant or {},
    )


class LedgerManager:
    """Append events and derive current state. No commit — the caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_event(
        self,
        *,
        user_id: int,
        provider_id: str,
        state: ProvisionState,
        grant: dict[str, Any] | None = None,
        external_ref: str | None = None,
        detail: str | None = None,
        partial: dict[str, Any] | None = None,
    ) -> ProvisioningEvent:
        """Append one ledger event; flush to assign its id. Never updates a prior event."""
        event = ProvisioningEvent(
            user_id=user_id,
            provider_id=provider_id,
            state=state,
            grant=grant or {},
            external_ref=external_ref,
            detail=detail,
            partial=partial,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def current_entry(self, user_id: int, provider_id: str) -> LedgerEntry | None:
        """The current state of one ``(user, provider)`` grant (its latest event), or None."""
        row = (
            await self._session.execute(
                select(ProvisioningEvent)
                .where(
                    ProvisioningEvent.user_id == user_id,
                    ProvisioningEvent.provider_id == provider_id,
                )
                .order_by(ProvisioningEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return _to_entry(row) if row is not None else None

    async def history(self, user_id: int, provider_id: str) -> list[ProvisioningEvent]:
        """The full event log for one ``(user, provider)``, oldest first."""
        return list(
            (
                await self._session.execute(
                    select(ProvisioningEvent)
                    .where(
                        ProvisioningEvent.user_id == user_id,
                        ProvisioningEvent.provider_id == provider_id,
                    )
                    .order_by(ProvisioningEvent.id)
                )
            )
            .scalars()
            .all()
        )

    async def user_active_entries(self, user_id: int) -> list[LedgerEntry]:
        """One user's grants still in an active state — the dashboard's only ledger read.

        Scoped to ``user_id`` in SQL (not filtered in Python) so the per-user boundary is enforced
        at the query: a dashboard can never surface another user's tiles (non-negotiable #8).
        """
        latest_ids = (
            select(func.max(ProvisioningEvent.id))
            .where(ProvisioningEvent.user_id == user_id)
            .group_by(ProvisioningEvent.provider_id)
            .scalar_subquery()
        )
        rows = (
            (
                await self._session.execute(
                    select(ProvisioningEvent)
                    .where(ProvisioningEvent.id.in_(latest_ids))
                    .order_by(ProvisioningEvent.id)
                )
            )
            .scalars()
            .all()
        )
        return [_to_entry(row) for row in rows if row.state in _ACTIVE_STATES]

    async def active_entries(self) -> list[LedgerEntry]:
        """Current state of every grant still in an active state — what reconciliation walks."""
        latest_ids = (
            select(func.max(ProvisioningEvent.id))
            .group_by(ProvisioningEvent.user_id, ProvisioningEvent.provider_id)
            .scalar_subquery()
        )
        rows = (
            (
                await self._session.execute(
                    select(ProvisioningEvent)
                    .where(ProvisioningEvent.id.in_(latest_ids))
                    .order_by(ProvisioningEvent.id)
                )
            )
            .scalars()
            .all()
        )
        return [_to_entry(row) for row in rows if row.state in _ACTIVE_STATES]
