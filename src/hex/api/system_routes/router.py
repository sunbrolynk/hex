"""System endpoints: health, version, setup status + unlock."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.__version__ import __version__
from hex.api.auth_routes.dependencies import require_user
from hex.api.guards import BOOTSTRAP_COOKIE, require_bootstrap_phase, require_bootstrap_session
from hex.api.schemas import HealthResponse, SetupStatusResponse, SetupUnlockRequest, WireResponse
from hex.audit import AuditSigner
from hex.authentik import AuthentikError, AuthentikUnreachable, wire_authentik
from hex.database import AuditLogManager, SetupStateManager, User, get_session
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
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatusResponse:
    """Consume the out-of-band setup token to enter bootstrap mode.

    Throttled and enumeration-resistant: a wrong, expired, or already-consumed token all return
    the same 401, and once a client has too many *failures* it gets 429 (a correct token never
    costs budget). Sustained failures past the lockout threshold burn the token and freeze the
    endpoint with 423 until HEx restarts. On success, advances FIRST_RUN → BOOTSTRAP and sets the
    ``hex_bootstrap`` session cookie. Every outcome is audited.
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
        session_token = await manager.begin_bootstrap(body.token, audit, actor=actor)
        phase = await manager.current_phase() if session_token is not None else None
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc

    if session_token is None or phase is None:
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
    response.set_cookie(
        BOOTSTRAP_COOKIE,
        session_token,
        httponly=True,
        secure=request.app.state.settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return SetupStatusResponse(phase=phase, setup_required=phase != SetupPhase.COMPLETE)


@router.post("/setup/wire")
async def setup_wire(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _phase: Annotated[None, Depends(require_bootstrap_phase)],
    _bootstrap: Annotated[None, Depends(require_bootstrap_session)],
) -> WireResponse:
    """Drive first-run Authentik wiring: verify, read back the secret, rotate to a scoped token.

    BOOTSTRAP-only and bound to the bootstrap session (the guards). The bootstrap token and
    read-back secrets stay server-side; the response carries only the public client_id. Fail-secure:
    any wiring failure is audited and surfaced (502/503) with nothing persisted, leaving the install
    in BOOTSTRAP to retry.
    """
    state = request.app.state
    try:
        result = await wire_authentik(
            settings=state.settings,
            http=state.http,
            broker=state.secrets,
            session=session,
            audit_signer=state.audit_signer,
        )
    except AuthentikUnreachable as exc:
        await _audit_wiring_failure(session, state.audit_signer, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentik is not reachable yet; try again.",
        ) from exc
    except AuthentikError as exc:
        await _audit_wiring_failure(session, state.audit_signer, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Authentik wiring failed."
        ) from exc
    except Exception as exc:
        # Persist/encrypt/commit failures are none of the above; #7 still requires they be
        # audited — never let a privileged action fail as an unaudited 500.
        await _audit_wiring_failure(session, state.audit_signer, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentik wiring failed."
        ) from exc
    return WireResponse(ok=True, client_id=result.client_id, provider_pk=result.provider_pk)


@router.post("/setup/complete")
async def setup_complete(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    _phase: Annotated[None, Depends(require_bootstrap_phase)],
    _bootstrap: Annotated[None, Depends(require_bootstrap_session)],
) -> SetupStatusResponse:
    """Claim ownership and finish setup: BOOTSTRAP → COMPLETE, marking the caller the owner.

    Requires the bootstrap session (proof of unlock) AND an authenticated OIDC session. Single-use:
    the first valid claim wins; a second (or a lost race) returns 409. Clears the bootstrap cookie.
    """
    audit = AuditLogManager(session, request.app.state.audit_signer)
    try:
        claimed = await SetupStateManager(session).complete_setup(
            user.id, audit, actor=f"user:{user.id}"
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    if not claimed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="setup already completed")
    response.delete_cookie(BOOTSTRAP_COOKIE, path="/")
    return SetupStatusResponse(phase=SetupPhase.COMPLETE, setup_required=False)


async def _audit_wiring_failure(session: AsyncSession, signer: AuditSigner, error: str) -> None:
    """Record a wiring failure (best-effort, no-leak); a partial txn is rolled back first."""
    try:
        await session.rollback()
        await AuditLogManager(session, signer).append(
            action=AuditAction.AUTHENTIK_WIRING_FAILED,
            severity=AuditSeverity.HIGH,
            result=AuditResult.FAILURE,
            actor="system",
            meta={"error": error},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        log.error("audit write failed for authentik.wiring.failed", exc_info=True)


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
