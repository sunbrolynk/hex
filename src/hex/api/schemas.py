"""Central API schemas."""

from pydantic import BaseModel

from hex.database.models import SetupPhase


class HealthResponse(BaseModel):
    """Liveness payload for ``GET /health``."""

    status: str
    version: str


class SetupStatusResponse(BaseModel):
    """First-run status for ``GET /setup/status``. Reveals only the phase — no secrets."""

    phase: SetupPhase
    setup_required: bool
