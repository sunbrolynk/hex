"""Provider-contract value types — the frozen vocabulary the lifecycle engine and every provider
share (docs/PROVIDER_CONTRACT.md, ADR 0002).

These are deliberately decoupled from the database: providers receive ``ProviderUser`` and
``LedgerEntry`` value objects, never SQLAlchemy models, so a provider never imports the database.
The ledger manager maps DB rows to/from these.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class IntegrationMode(StrEnum):
    """Axis 1 — how HEx grants/revokes access. Exactly four; no fifth (ADR 0002)."""

    SSO_GROUP = "sso_group"  # add to an Authentik group/claim
    API_LOCAL = "api_local"  # call the app's own user-management API
    EXTERNAL_INVITE = "external_invite"  # send a share/invite the user claims externally
    MANUAL = "manual"  # no API/SSO; render owner-authored instructions


class IdentityOwner(StrEnum):
    """Axis 2 — who owns the user record; governs whether deprovision is symmetric or a revoke."""

    AUTHENTIK = "authentik"  # remove from group / deactivate in Authentik
    PROVIDER = "provider"  # delete/disable via the app API
    EXTERNAL = "external"  # asymmetric: revoke the share only — HEx cannot delete the account
    NONE = "none"  # no per-user downstream record


class Capability(StrEnum):
    """Optional provider methods that are meaningful for a given provider."""

    WIDGET_DATA = "widget_data"  # per-user dashboard payload
    AVAILABLE_GRANTS = "available_grants"  # owner-selectable grant tiers


class ProvisionState(StrEnum):
    """State of a ``(user, provider)`` grant — used by ``provision`` results and the ledger.

    ``provision`` never returns ``REVOKED`` (that is reached only via ``deprovision``); the rest
    are valid provision outcomes. ``FAILED`` is the safe default for ANY uncertainty.
    """

    GRANTED = "granted"  # access is live now
    PENDING_MANUAL = "pending_manual"  # awaiting owner-authored manual steps
    PENDING_EXTERNAL_CLAIM = "pending_external_claim"  # invite/share sent; awaiting external claim
    PARTIAL = "partial"  # multi-step grant partly applied; detail records what did
    FAILED = "failed"  # could not provision — the safe default for uncertainty
    REVOKED = "revoked"  # access removed (ledger-only; from deprovision)


class Grant(BaseModel):
    """Base for a provider's structured grant object. Subclass per provider; the subclass *is* the
    schema (``grant_schema`` = ``model_json_schema``) and the server-side validator. Not a boolean.
    """

    model_config = ConfigDict(extra="forbid")  # reject unknown grant fields (fail-closed input)


@dataclass(frozen=True)
class ProviderUser:
    """The minimal user view passed to a provider — never the DB model."""

    id: int
    username: str | None
    email: str | None


@dataclass(frozen=True)
class LedgerEntry:
    """The contract's view of a ledger row, passed to ``deprovision``/``status`` so the provider has
    the ``external_ref`` it needs to act. Keyed by ``(user_id, provider_id)`` so it is meaningful
    standalone (e.g. reconciliation iterating entries). The grant is the stored structured object
    (a raw mapping; the provider can re-parse it with ``parse_grant``)."""

    user_id: int
    provider_id: str
    state: ProvisionState
    external_ref: str | None
    grant: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigStatus:
    """Outcome of ``validate_config`` at boot — a provider that can't validate is disabled."""

    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of ``provision``. ``instructions`` carries the manual steps for ``PENDING_MANUAL``;
    ``claim_url`` the external claim target for ``PENDING_EXTERNAL_CLAIM``; ``detail`` records what
    happened (especially the exact partial steps for ``PARTIAL`` and the reason for ``FAILED``)."""

    state: ProvisionState
    external_ref: str | None = None
    instructions: str | None = None
    claim_url: str | None = None
    detail: str | None = None
    # Structured record of exactly which steps/sub-grants succeeded — required for PARTIAL so a
    # later deprovision/retry is precise (free-text ``detail`` is not enough). Stored in the ledger.
    partial: dict[str, Any] | None = None


@dataclass(frozen=True)
class DeprovisionResult:
    """Outcome of ``deprovision``. Idempotent: an already-revoked grant returns ``revoked=True``,
    not an error. For ``identity_owner=external`` this means the share was revoked, not an account
    deleted."""

    revoked: bool
    detail: str | None = None


@dataclass(frozen=True)
class DownstreamStatus:
    """Observed downstream state, for reconciliation/drift detection. ``present`` = the access or
    identity still exists downstream."""

    present: bool
    detail: str | None = None


@dataclass(frozen=True)
class WidgetPayload:
    """Per-user dashboard data from a provider. ``data`` is provider-shaped and MUST be scoped to
    the one requesting user — never another user's data."""

    data: dict[str, Any]


@dataclass(frozen=True)
class GrantTemplate:
    """A tier/option the owner can offer for a provider; ``grant`` is the pre-filled structured
    grant (validated against the provider's grant model before use)."""

    key: str
    label: str
    grant: dict[str, Any]
    description: str | None = None
