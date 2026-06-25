"""Data access for HEx users (keyed to an Authentik ``sub``)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import User

# Reserved sub for the local break-glass owner — a local identity (ADR 0008), never an Authentik
# user. Namespaced with "local:" so it can never collide with a real OIDC subject.
BREAKGLASS_SUB = "local:breakglass"  # noqa: S105 — an identifier, not a credential


class UserManager:
    """Upsert + read users from validated OIDC identity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, *, authentik_sub: str, username: str | None, email: str | None) -> User:
        """Find the user by ``authentik_sub`` (create on first login); refresh profile fields.

        No commit — the caller owns the txn so user + session + audit commit atomically. Role
        (``is_owner``) is never set here; owner determination lands in Slice 3.
        """
        user = (
            await self._session.execute(select(User).where(User.authentik_sub == authentik_sub))
        ).scalar_one_or_none()
        if user is None:
            user = User(authentik_sub=authentik_sub, username=username, email=email)
            self._session.add(user)
            await self._session.flush()  # assign user.id within the transaction
        else:
            user.username = username
            user.email = email
        return user

    async def ensure_breakglass_owner(self, username: str) -> User:
        """Get-or-create the single local break-glass owner (``is_owner`` + ``is_break_glass``).

        No commit — the caller owns the txn so user + session + audit commit atomically.
        """
        user = (
            await self._session.execute(select(User).where(User.authentik_sub == BREAKGLASS_SUB))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                authentik_sub=BREAKGLASS_SUB,
                username=username,
                is_owner=True,
                is_break_glass=True,
            )
            self._session.add(user)
            await self._session.flush()  # assign user.id within the transaction
        else:
            user.username = username  # keep in sync with the configured break-glass username
        return user
