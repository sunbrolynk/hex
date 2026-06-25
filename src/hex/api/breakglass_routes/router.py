"""Break-glass emergency login — reachable only on the LAN-bound listener (ADR 0008, §13).

Disabled by default and gated by ``require_breakglass_listener`` (Slice 4-2a). Accepts the one local
owner credential plus offline TOTP, but only while Authentik is unreachable (the condition gate).
Every attempt is a HIGH-severity audit event; repeated failures trip an auto-clearing cooldown
lockout. The browser only ever receives the opaque session cookie.
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import SESSION_COOKIE
from hex.api.guards import require_breakglass_listener
from hex.api.schemas import BreakGlassLoginRequest, UserResponse
from hex.audit import AuditSigner
from hex.breakglass import BreakGlassConfig, BreakGlassOutcome, verify_breakglass
from hex.breakglass.idp_health import idp_healthy
from hex.breakglass.lockout import CooldownLimiter
from hex.database import AuditLogManager, SessionManager, UserManager, get_session
from hex.database.models import AuditAction, AuditResult, AuditSeverity

log = logging.getLogger("hex.breakglass")
router = APIRouter(tags=["break-glass"])

_TARGET = "breakglass"


async def _audit_failure(
    session: AsyncSession,
    signer: AuditSigner,
    action: AuditAction,
    actor: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Record a break-glass failure (HIGH, best-effort); an audit hiccup must not become a 500."""
    try:
        await AuditLogManager(session, signer).append(
            action=action,
            severity=AuditSeverity.HIGH,
            result=AuditResult.FAILURE,
            actor=actor,
            target=_TARGET,
            meta=meta or {},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        log.error("audit write failed for %s", action, exc_info=True)


@router.post("/auth/breakglass", dependencies=[Depends(require_breakglass_listener)])
async def breakglass_login(
    body: BreakGlassLoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Authenticate the local owner credential when Authentik is down; mint an owner session.

    Fail-secure and loud: a wrong credential, an active cooldown, and a reachable IdP each deny
    without revealing why beyond the (LAN-only) condition signal, and every outcome is audited HIGH.
    """
    app = request.app
    settings = app.state.settings
    config: BreakGlassConfig = app.state.breakglass
    lockout: CooldownLimiter = app.state.breakglass_lockout
    signer: AuditSigner = app.state.audit_signer
    actor = f"client:{request.client.host if request.client else 'unknown'}"
    now = time.monotonic()

    if lockout.locked(now):
        await _audit_failure(session, signer, AuditAction.BREAKGLASS_LOCKED_OUT, actor)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
        )

    healthy = await idp_healthy(settings.authentik_server_base_url, app.state.http)
    outcome = verify_breakglass(
        config,
        username=body.username,
        password_attempt=body.password,
        totp_code=body.totp,
        idp_healthy=healthy,
    )

    if outcome is BreakGlassOutcome.OK:
        try:
            user = await UserManager(session).ensure_breakglass_owner(config.username)
            raw = await SessionManager(
                session, lifetime_seconds=settings.breakglass_session_lifetime_seconds
            ).create(user)
            # Fail-closed: the session + success audit commit together, or both roll back.
            await AuditLogManager(session, signer).append(
                action=AuditAction.BREAKGLASS_SUCCEEDED,
                severity=AuditSeverity.HIGH,
                result=AuditResult.SUCCESS,
                actor=actor,
                target=f"user:{user.id}",
            )
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
            ) from exc
        lockout.reset()
        response.set_cookie(
            SESSION_COOKIE,
            raw,
            max_age=settings.breakglass_session_lifetime_seconds,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        return UserResponse(id=user.id, username=user.username, email=user.email, is_owner=True)

    # A reachable IdP closes the path; this is not a credential failure, so it never counts toward
    # lockout (else a healthy Authentik would lock the owner out).
    if outcome is BreakGlassOutcome.CONDITION_NOT_MET:
        await _audit_failure(
            session, signer, AuditAction.BREAKGLASS_FAILED, actor, {"reason": "idp_reachable"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Break-glass is unavailable while Authentik is reachable. Use normal sign-in.",
        )

    # BAD_CREDENTIALS (or DISABLED, which the listener guard already blocks): generic, counted.
    lockout.record_failure(now)
    await _audit_failure(
        session, signer, AuditAction.BREAKGLASS_FAILED, actor, {"reason": "bad_credentials"}
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid break-glass credentials"
    )
