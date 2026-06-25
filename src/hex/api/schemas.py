"""Central API schemas."""

from pydantic import BaseModel, ConfigDict, Field

from hex.database.models import SetupPhase


class HealthResponse(BaseModel):
    """Liveness payload for ``GET /health``."""

    status: str
    version: str


class SetupStatusResponse(BaseModel):
    """First-run status for ``GET /setup/status``. Reveals only the phase — no secrets."""

    phase: SetupPhase
    setup_required: bool


class SetupUnlockRequest(BaseModel):
    """Body for ``POST /setup/unlock``: the out-of-band setup token from the container logs."""

    token: str = Field(min_length=1, max_length=512)


class WireResponse(BaseModel):
    """Outcome of ``POST /setup/wire``. Reports the public client_id only — never a secret."""

    ok: bool
    client_id: str
    provider_pk: int


class UserResponse(BaseModel):
    """Current-user payload for ``GET /auth/me``. No tokens, no Authentik internals."""

    id: int
    username: str | None
    email: str | None
    is_owner: bool


class BreakGlassLoginRequest(BaseModel):
    """Body for ``POST /auth/breakglass``: local owner credential + offline TOTP."""

    model_config = ConfigDict(extra="forbid")  # reject unknown fields (SECURITY_MODEL §10)

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    totp: str = Field(min_length=1, max_length=16)
