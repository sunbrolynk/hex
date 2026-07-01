"""Invite capability logic + data access (single-use, expiring; non-negotiable #5).

The token is high-entropy (≥256 bits), so a SHA-256 hash + indexed lookup is the right at-rest form
(same reasoning as the setup token / session tokens). Only the hash is stored; the raw token is
returned to the owner once. No commit — the caller owns the transaction.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
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

    async def accept(self, raw_token: str) -> Invite | None:
        """Atomically consume the invite (hard cap of 1) and return it, or None if unacceptable.

        Single-use is a DB guarantee: the conditional UPDATE's ``accepted_at IS NULL`` WHERE clause
        means only the first of two concurrent accepts flips the row (rowcount == 1) — no read-then-
        write race. Expiry is checked after (the burn is uncommitted, so the caller rolls back and
        the invite is not spent if expired). No commit — the caller owns the transaction.
        """
        token_hash = hash_token(raw_token)
        now = datetime.now(UTC)
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Invite)
                .where(
                    Invite.token_hash == token_hash,
                    Invite.accepted_at.is_(None),
                    Invite.revoked_at.is_(None),
                )
                .values(accepted_at=now)
            ),
        )
        if result.rowcount != 1:
            return None
        invite = (
            await self._session.execute(select(Invite).where(Invite.token_hash == token_hash))
        ).scalar_one()
        if _aware(invite.expires_at) <= now:
            return None  # expired — caller rolls back, so the burn is undone (not spent)
        return invite

    async def link_to_user(self, nonce: str, user_id: int) -> Invite | None:
        """Bind an accepted invite to the user who completed enrollment; None if no match.

        Matched by the acceptance nonce — carried in the signed ``hex_invite_nonce`` claim (primary,
        6-2d) or the httponly cookie (fallback, 6-2b); both hash to ``accept_nonce_hash``.
        First-wins via ``accepted_by IS NULL`` so a replay can't re-bind; the nonce hash only exists
        on an accepted invite. No commit — caller owns the txn (binds atomically with login).
        """
        nonce_hash = hash_token(nonce)
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Invite)
                .where(Invite.accept_nonce_hash == nonce_hash, Invite.accepted_by.is_(None))
                .values(accepted_by=user_id)
            ),
        )
        if result.rowcount != 1:
            return None
        # Re-select by the just-written accepted_by too: with rowcount==1 exactly one row carries
        # it, so this is single regardless of accept_nonce_hash not being unique-constrained.
        return (
            await self._session.execute(
                select(Invite).where(
                    Invite.accept_nonce_hash == nonce_hash, Invite.accepted_by == user_id
                )
            )
        ).scalar_one()

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
