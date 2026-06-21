"""System endpoints: health, version, setup status + unlock."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.__version__ import __version__
from hex.api.schemas import HealthResponse, SetupStatusResponse, SetupUnlockRequest
from hex.database import SetupStateManager, get_session
from hex.database.models import SetupPhase
from hex.setup import AttemptLimiter

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
    costs budget). On success, advances FIRST_RUN → BOOTSTRAP.
    """
    limiter: AttemptLimiter = request.app.state.setup_limiter
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if limiter.blocked(client, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
        )

    manager = SetupStateManager(session)
    try:
        advanced = await manager.begin_bootstrap(body.token)
        phase = await manager.current_phase() if advanced else None
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc

    if not advanced or phase is None:
        limiter.record_failure(client, now)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid setup token")
    return SetupStatusResponse(phase=phase, setup_required=phase != SetupPhase.COMPLETE)
