"""System endpoints: health, version, setup status + unlock."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.__version__ import __version__
from hex.api.schemas import HealthResponse, SetupStatusResponse, SetupUnlockRequest
from hex.audit import AuditSigner
from hex.database import AuditLogManager, SetupStateManager, get_session
from hex.database.models import AuditAction, AuditResult, AuditSeverity, SetupPhase
from hex.setup import AttemptLimiter, LockoutCounter

log = logging.getLogger("hex.setup")
_SETUP_TARGET = "setup_state:1"

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> HealthResponse:
    """Report liveness. Unauthenticated; exposes no secrets or user data."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/setup/status")
async def setup_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatusResponse:
    """Report whether first-run setup is still required. Unauthenticated; no secrets."""
    try:
        phase = await SetupStateManager(session).current_phase()
    except SQLAlchemyError as exc:
        # DB unreachable during boot/migration → 503 (try later), never a debug 500 stack.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return SetupStatusResponse(phase=phase, setup_required=phase != SetupPhase.COMPLETE)


@router.post("/setup/unlock")
async def setup_unlock(
    body: SetupUnlockRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatusResponse:
    """Consume the out-of-band setup token to enter bootstrap mode.

    Throttled and enumeration-resistant: a wrong, expired, or already-consumed token all return
    the same 401, and once a client has too many *failures* it gets 429 (a correct token never
    costs budget). Sustained failures past the lockout threshold burn the token and freeze the
    endpoint with 423 until HEx restarts. On success, advances FIRST_RUN → BOOTSTRAP. Every
    outcome is audited.
    """
    signer: AuditSigner = request.app.state.audit_signer
    limiter: AttemptLimiter = request.app.state.setup_limiter
    lockout: LockoutCounter = request.app.state.setup_lockout
    threshold: int = request.app.state.settings.setup_unlock_lockout_threshold
    client = request.client.host if request.client else "unknown"
    actor = f"client:{client}"
    now = time.monotonic()
    audit = AuditLogManager(session, signer)

    # Frozen by a prior lockout: the token is already burned; only a restart recovers.
    if lockout.frozen:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="setup locked")

    if limiter.blocked(client, now):
        await _audit_failure(session, audit, AuditAction.SETUP_UNLOCK_THROTTLED, actor)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
        )

    manager = SetupStateManager(session)
    try:
        advanced = await manager.begin_bootstrap(body.token, audit, actor=actor)
        phase = await manager.current_phase() if advanced else None
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc

    if not advanced or phase is None:
        limiter.record_failure(client, now)
        count = lockout.record(threshold)
        if lockout.frozen:
            try:
                await manager.burn_setup_token(audit, actor=actor, failure_count=count)
            except SQLAlchemyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
                ) from exc
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="setup locked")
        await _audit_failure(session, audit, AuditAction.SETUP_UNLOCK_FAILED, actor)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid setup token")
    return SetupStatusResponse(phase=phase, setup_required=phase != SetupPhase.COMPLETE)


async def _audit_failure(
    session: AsyncSession, audit: AuditLogManager, action: AuditAction, actor: str
) -> None:
    """Record a pure-failure event, best-effort; an audit hiccup must never become a 500."""
    try:
        await audit.append(
            action=action,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.FAILURE,
            actor=actor,
            target=_SETUP_TARGET,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        log.error("audit write failed for %s", action.value, exc_info=True)
