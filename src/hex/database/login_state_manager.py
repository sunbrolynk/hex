"""Transient, one-time OIDC login-flow state (CSRF state + nonce + PKCE verifier)."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import OIDCLoginState
from hex.setup import hash_token


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class LoginStateManager:
    """Persist and one-time-consume the state for an in-flight Authorization-Code round-trip."""

    def __init__(self, session: AsyncSession, *, ttl_seconds: int) -> None:
        self._session = session
        self._ttl = ttl_seconds

    async def create(self, *, state: str, nonce: str, code_verifier: str, redirect_to: str) -> None:
        """Store flow state keyed by ``hash(state)``; raw state stays in the URL only. No commit."""
        self._session.add(
            OIDCLoginState(
                state_hash=hash_token(state),
                nonce=nonce,
                code_verifier=code_verifier,
                redirect_to=redirect_to,
                expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl),
            )
        )

    async def consume(self, state: str) -> OIDCLoginState | None:
        """Fetch + delete (one-time) the row for ``state``; None if missing/expired. No commit."""
        row = await self._session.get(OIDCLoginState, hash_token(state))
        if row is None:
            return None
        await self._session.delete(row)  # single-use, regardless of outcome
        if _aware(row.expires_at) <= datetime.now(UTC):
            return None
        return row

    async def purge_expired(self) -> int:
        """GC expired login-flow rows; returns the number removed. No commit."""
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(OIDCLoginState).where(OIDCLoginState.expires_at <= datetime.now(UTC))
            ),
        )
        return result.rowcount
