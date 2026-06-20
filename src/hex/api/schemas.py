"""Central API schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload for ``GET /health``."""

    status: str
    version: str
