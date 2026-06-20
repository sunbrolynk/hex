"""System endpoints: health, version, status."""

from fastapi import APIRouter

from hex.__version__ import __version__
from hex.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> HealthResponse:
    """Report liveness. Unauthenticated; exposes no secrets or user data."""
    return HealthResponse(status="ok", version=__version__)
