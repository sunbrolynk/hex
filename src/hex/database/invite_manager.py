"""Invite capability logic + data access (single-use, expiring; non-negotiable #5).

The token is high-entropy (≥256 bits), so a SHA-256 hash + indexed lookup is the right at-rest form
(same reasoning as the setup token / session tokens). Only the hash is stored; the raw token is
returned to the owner once. No commit — the caller owns the transaction.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import Invite
from hex.setup import hash_token, mint_token


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class InviteManager:
    """Create, list, revoke, and resolve invite capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner_id: int,
        default_grants: dict[str, Any],
        requestable: list[str],
        ttl_seconds: int,
    ) -> tuple[Invite, str]:
        """Mint an invite; store its hash; return the row and the raw token (shown once)."""
        raw = mint_token()
        invite = Invite(
            token_hash=hash_token(raw),
            created_by=owner_id,
            default_grants=default_grants,
            requestable=requestable,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self._session.add(invite)
        await self._session.flush()
        return invite, raw

    async def list_all(self) -> list[Invite]:
        """Every invite, newest first (single-owner install)."""
        result = await self._session.execute(select(Invite).order_by(Invite.id.desc()))
        return list(result.scalars().all())

    async def revoke(self, invite_id: int) -> Invite | None:
        """Revoke an unaccepted, unrevoked invite; return it, or None if it can't be revoked."""
        invite = await self._session.get(Invite, invite_id)
        if invite is None or invite.revoked_at is not None or invite.accepted_at is not None:
            return None
        invite.revoked_at = datetime.now(UTC)
        return invite

    async def resolve_valid(self, raw_token: str) -> Invite | None:
        """The invite for ``raw_token`` iff still acceptable (unexpired, unrevoked, unaccepted)."""
        invite = (
            await self._session.execute(
                select(Invite).where(Invite.token_hash == hash_token(raw_token))
            )
        ).scalar_one_or_none()
        if invite is None or invite.revoked_at is not None or invite.accepted_at is not None:
            return None
        if _aware(invite.expires_at) <= datetime.now(UTC):
            return None
        return invite
