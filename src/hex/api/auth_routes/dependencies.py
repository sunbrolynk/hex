"""Auth dependencies. Identity comes from the server-side session cookie — never a header."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SessionManager, User, get_session

SESSION_COOKIE = "hex_session"


async def require_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the session cookie to a user, or 401. Trusts no proxy-injected identity header."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    lifetime = request.app.state.settings.session_lifetime_seconds
    user = await SessionManager(session, lifetime_seconds=lifetime).resolve(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user
