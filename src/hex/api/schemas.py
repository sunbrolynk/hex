"""Central API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hex.api.recipient import RecipientKind, normalize_recipient
from hex.database.models import SetupPhase


class TileResponse(BaseModel):
    """One dashboard tile — a service the user has been granted (read from the ledger)."""

    provider_id: str
    name: str
    category: str
    state: str  # ProvisionState value: granted / pending_* / partial
    integration_mode: str
    url: str | None  # owner-configured deep-link; None when not configured
    seamless: bool  # tile click drops straight in (SSO pass-through) where the mode allows


class DashboardResponse(BaseModel):
    """The signed-in user's personalized dashboard — strictly their own grants."""

    tiles: list[TileResponse]


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


class TierOption(BaseModel):
    """A grantable tier a provider offers. The owner picks the ``key``; the server resolves it to
    the structured grant — no owner-authored grant blobs cross the wire (ADR 0015)."""

    key: str
    label: str
    description: str | None = None


class ProviderSummary(BaseModel):
    """An integrated service the owner can grant/offer, for ``GET /providers`` (owner-only)."""

    id: str
    name: str
    category: str
    integration_mode: str
    tiers: list[TierOption]


class InviteCreateRequest(BaseModel):
    """Body for ``POST /invites`` (owner-only). Grants + requestable allowlist + TTL.

    ``default_grants`` maps ``provider_id → tier key`` (both validated against the registry
    server-side; the server resolves the key to the structured grant). ``requestable`` is a list of
    provider ids the user may later request — also registry-validated.
    """

    model_config = ConfigDict(extra="forbid")

    default_grants: dict[str, str] = Field(default_factory=dict)  # provider_id -> tier key
    requestable: list[str] = Field(default_factory=list)
    ttl_hours: int = Field(default=168, ge=1, le=8760)  # 1h … 1y; default 7 days
    # Optional "who" (owner-only). recipient + recipient_kind are all-or-nothing; the value is
    # validated + normalized per kind (email→RFC, phone→E.164, label→trimmed) — a bad value is 422.
    recipient: str | None = Field(default=None, max_length=320)
    recipient_kind: RecipientKind | None = None

    @model_validator(mode="after")
    def _normalize_recipient(self) -> "InviteCreateRequest":
        if (self.recipient is None) != (self.recipient_kind is None):
            raise ValueError("recipient and recipient_kind must be provided together")
        if self.recipient is not None and self.recipient_kind is not None:
            self.recipient = normalize_recipient(self.recipient_kind, self.recipient)
        return self


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
    recipient: str | None
    recipient_kind: str | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InviteListResponse(BaseModel):
    """A page of the owner's invite history plus the total for pagination."""

    items: list[InviteResponse]
    total: int
    limit: int
    offset: int


class InvitePreviewResponse(BaseModel):
    """What a valid invite offers, shown on the public acceptance/preview endpoint."""

    requestable: list[str]
    grant_providers: list[str]
    expires_at: datetime


class InviteAcceptResponse(BaseModel):
    """Acceptance outcome: where to send the user to enroll in Authentik."""

    enroll_url: str
