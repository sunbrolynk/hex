"""Server-side session store. The cookie carries the raw token; only its SHA-256 is persisted."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import User, UserSession
from hex.setup import hash_token, mint_token


def _aware(value: datetime) -> datetime:
    """Treat a tz-naive datetime (how SQLite round-trips one) as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SessionManager:
    """Create, resolve, and revoke server-side sessions (revocation is immediate)."""

    def __init__(self, session: AsyncSession, *, lifetime_seconds: int) -> None:
        self._session = session
        self._lifetime = lifetime_seconds

    async def create(self, user: User) -> str:
        """Mint a session; store its hash + expiry; return the raw cookie token. No commit."""
        raw = mint_token()
        self._session.add(
            UserSession(
                session_token_hash=hash_token(raw),
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(seconds=self._lifetime),
            )
        )
        return raw

    async def resolve(self, raw_token: str) -> User | None:
        """The session's user if the token is valid and unexpired; else None (fail-secure)."""
        row = await self._session.get(UserSession, hash_token(raw_token))
        if row is None or _aware(row.expires_at) <= datetime.now(UTC):
            return None
        return await self._session.get(User, row.user_id)

    async def revoke(self, raw_token: str) -> None:
        """Delete the session — immediate server-side revocation. Idempotent. No commit."""
        await self._session.execute(
            delete(UserSession).where(UserSession.session_token_hash == hash_token(raw_token))
        )

    async def purge_expired(self) -> int:
        """GC expired sessions; returns the number removed. No commit."""
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(UserSession).where(UserSession.expires_at <= datetime.now(UTC))
            ),
        )
        return result.rowcount
