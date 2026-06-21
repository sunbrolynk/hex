"""System endpoints: health, version, setup status."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hex.__version__ import __version__
from hex.api.schemas import HealthResponse, SetupStatusResponse
from hex.database import SetupStateManager, get_session
from hex.database.models import SetupPhase

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
    phase = await SetupStateManager(session).current_phase()
    return SetupStatusResponse(phase=phase, setup_required=phase != SetupPhase.COMPLETE)
