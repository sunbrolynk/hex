"""Auth dependencies. Identity comes from the server-side session cookie — never a header."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from hex.authentik import resolve_oidc_config
from hex.database import AuthentikIntegrationManager, SessionManager, User, get_session
from hex.oidc import OIDCClient, OIDCConfig
from hex.secrets import InvalidToken

SESSION_COOKIE = "hex_session"
log = logging.getLogger("hex.auth")


async def get_oidc_client(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OIDCClient:
    """Build the OIDC client from the per-request resolved config (env over DB-wired).

    Fail-secure: if a persisted client secret can't be decrypted (wrong/rotated KEK), treat the
    integration as unconfigured so login returns a clean 503, never a 500 that leaks a stack.
    """
    integration = await AuthentikIntegrationManager(session).get()
    try:
        config = resolve_oidc_config(
            request.app.state.settings, integration, request.app.state.secrets
        )
    except InvalidToken:
        log.error("persisted Authentik client secret failed to decrypt — treating as unconfigured")
        config = OIDCConfig()
    return OIDCClient(config, request.app.state.http, request.app.state.discovery_cache)


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


async def require_owner(user: Annotated[User, Depends(require_user)]) -> User:
    """Require the authenticated user to be the owner. The owner/user boundary is server-enforced.

    Never trusts a client-supplied role; ``is_owner`` is read from the server-side user record.
    """
    if not user.is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner only")
    return user
