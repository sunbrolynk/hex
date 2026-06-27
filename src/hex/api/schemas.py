"""Central API schemas."""

from datetime import datetime
from typing import Any

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


class InviteCreateRequest(BaseModel):
    """Body for ``POST /invites`` (owner-only). Default grants + requestable allowlist + TTL."""

    model_config = ConfigDict(extra="forbid")

    default_grants: dict[str, dict[str, Any]] = Field(default_factory=dict)
    requestable: list[str] = Field(default_factory=list)
    ttl_hours: int = Field(default=168, ge=1, le=8760)  # 1h … 1y; default 7 days


class InviteCreatedResponse(BaseModel):
    """Response to invite creation. The raw token is returned exactly once."""

    id: int
    token: str
    expires_at: datetime


class InviteResponse(BaseModel):
    """Invite metadata for the owner list — never the token."""

    id: int
    status: str  # active | accepted | revoked | expired
    requestable: list[str]
    grant_providers: list[str]
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InvitePreviewResponse(BaseModel):
    """What a valid invite offers, shown on the public acceptance/preview endpoint."""

    requestable: list[str]
    grant_providers: list[str]
    expires_at: datetime
