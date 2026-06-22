"""Auth endpoints: OIDC login (BFF), callback, current user, logout.

The browser only ever holds the opaque session cookie — no OIDC/access/ID tokens (non-negotiable
#9). The Authorization-Code exchange is server-side; every login/logout outcome is audited.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import SESSION_COOKIE, require_user
from hex.api.schemas import UserResponse
from hex.database import (
    AuditLogManager,
    LoginStateManager,
    SessionManager,
    User,
    UserManager,
    get_session,
)
from hex.database.models import AuditAction, AuditResult, AuditSeverity
from hex.oidc import OIDCClient, OIDCError, make_nonce, make_pkce_pair, make_state

log = logging.getLogger("hex.auth")
router = APIRouter(tags=["auth"])


def _safe_redirect(path: str | None) -> str:
    """Same-origin path only — blocks open redirects (scheme/host/protocol-relative) + CR/LF."""
    if (
        path
        and path.startswith("/")
        and not path.startswith(("//", "/\\"))
        and not any(ch < " " for ch in path)  # reject control chars (CR/LF/TAB) defensively
    ):
        return path
    return "/"


def _callback_url(request: Request) -> str:
    return str(request.url_for("auth_callback"))


@router.get("/auth/login")
async def auth_login(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    next: str = "/",
) -> RedirectResponse:
    """Begin the Authorization-Code flow: stash one-time state, redirect to Authentik."""
    oidc: OIDCClient = request.app.state.oidc
    if not oidc.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC not configured"
        )
    settings = request.app.state.settings
    state, nonce = make_state(), make_nonce()
    verifier, challenge = make_pkce_pair()
    login_state = LoginStateManager(session, ttl_seconds=settings.oidc_login_state_ttl_seconds)
    await login_state.purge_expired()
    await login_state.create(
        state=state, nonce=nonce, code_verifier=verifier, redirect_to=_safe_redirect(next)
    )
    try:
        url = await oidc.authorize_url(
            state=state, nonce=nonce, code_challenge=challenge, redirect_uri=_callback_url(request)
        )
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC discovery unavailable"
        ) from exc
    await session.commit()
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Validate state, exchange the code server-side, create a session, set the cookie."""
    oidc: OIDCClient = request.app.state.oidc
    settings = request.app.state.settings
    actor = f"client:{request.client.host if request.client else 'unknown'}"
    audit = AuditLogManager(session, request.app.state.audit_signer)

    async def fail(reason: str) -> RedirectResponse:
        try:
            await audit.append(
                action=AuditAction.OIDC_LOGIN_FAILED,
                severity=AuditSeverity.NOTICE,
                result=AuditResult.FAILURE,
                actor=actor,
                meta={"reason": reason},
            )
            await session.commit()
        except Exception:
            await session.rollback()
            log.error("audit write failed for oidc.login.failed (%s)", reason, exc_info=True)
        return RedirectResponse("/?login=failed", status_code=status.HTTP_302_FOUND)

    if error or not code or not state:
        return await fail("authentik_error" if error else "missing_params")

    login_state = LoginStateManager(session, ttl_seconds=settings.oidc_login_state_ttl_seconds)
    flow = await login_state.consume(state)
    if flow is None:
        return await fail("invalid_state")
    # Burn the one-time state in its own commit, so it stays consumed even if a later rollback
    # (e.g. a failed success-audit) unwinds the session txn. expire_on_commit=False keeps `flow`
    # readable afterwards.
    await session.commit()

    try:
        claims = await oidc.exchange_code(
            code=code,
            code_verifier=flow.code_verifier,
            redirect_uri=_callback_url(request),
            nonce=flow.nonce,
        )
    except OIDCError:
        return await fail("exchange_failed")

    user = await UserManager(session).upsert(
        authentik_sub=claims.sub, username=claims.preferred_username, email=claims.email
    )
    raw = await SessionManager(session, lifetime_seconds=settings.session_lifetime_seconds).create(
        user
    )
    try:
        # Fail-closed: the session + login audit commit together; a failed write rolls both back.
        await audit.append(
            action=AuditAction.OIDC_LOGIN_SUCCEEDED,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.SUCCESS,
            actor=actor,
            target=f"user:{user.id}",
        )
        await session.commit()
    except Exception:
        await session.rollback()
        return await fail("persist_failed")

    response = RedirectResponse(_safe_redirect(flow.redirect_to), status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/auth/me")
async def auth_me(user: Annotated[User, Depends(require_user)]) -> UserResponse:
    """The authenticated user, or 401 via ``require_user``."""
    return UserResponse(
        id=user.id, username=user.username, email=user.email, is_owner=user.is_owner
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Revoke the session server-side (immediate) and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        manager = SessionManager(
            session, lifetime_seconds=request.app.state.settings.session_lifetime_seconds
        )
        user = await manager.resolve(token)
        await manager.revoke(token)
        if user is not None:
            await AuditLogManager(session, request.app.state.audit_signer).append(
                action=AuditAction.OIDC_LOGOUT,
                severity=AuditSeverity.NOTICE,
                result=AuditResult.SUCCESS,
                actor=f"user:{user.id}",
                target=f"user:{user.id}",
            )
        await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
