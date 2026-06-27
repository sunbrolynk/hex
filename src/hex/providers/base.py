"""The provider contract — the one interface every integrated app implements (the spine).

There is exactly one contract (this interface); each provider declares one of four integration
modes and one of four identity owners (the two axes). All network-touching methods are async and
MUST be defensively coded against timeouts, partial failures, and hostile/malformed responses, and
MUST fail closed: on any uncertainty, ``provision`` returns ``FAILED`` rather than optimistic
success. See docs/PROVIDER_CONTRACT.md.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from hex.providers.types import (
    Capability,
    ConfigStatus,
    DeprovisionResult,
    DownstreamStatus,
    Grant,
    GrantTemplate,
    IdentityOwner,
    IntegrationMode,
    LedgerEntry,
    ProviderUser,
    ProvisionResult,
    WidgetPayload,
)


class Provider(ABC):
    """One integrated app. Subclasses live one-per-file in ``hex/providers`` and set the class-level
    declarations, point ``grant_model`` at their Pydantic grant, and implement the async methods."""

    # --- static declaration (set by each subclass) ---
    id: ClassVar[str]  # stable slug, e.g. "jellyfin"
    name: ClassVar[str]  # display name
    category: ClassVar[str]  # "media", "requests", "docs", …
    integration_mode: ClassVar[IntegrationMode]
    identity_owner: ClassVar[IdentityOwner]
    capabilities: ClassVar[frozenset[Capability]] = frozenset()
    grant_model: ClassVar[type[Grant]]  # the provider's Pydantic grant schema

    def grant_schema(self) -> dict[str, Any]:
        """JSON Schema for the structured grant — drives the owner UI and documents the shape."""
        return self.grant_model.model_json_schema()

    def parse_grant(self, raw: Mapping[str, Any]) -> Grant:
        """Validate an owner-supplied grant blob against this provider's schema. Raises on invalid;
        never accept an unvalidated grant (docs/PROVIDER_CONTRACT.md)."""
        return self.grant_model.model_validate(dict(raw))

    @abstractmethod
    async def validate_config(self) -> ConfigStatus:
        """Verify credentials, connectivity, and least-privilege scope at boot. A provider that
        cannot validate is disabled, not silently broken."""

    @abstractmethod
    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        """Idempotent. Return a state plus, where applicable, the external_ref and the
        instructions/claim URL to show the user. On ANY uncertainty return ``FAILED``."""

    @abstractmethod
    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        """Idempotent and aggressive. For ``identity_owner=external`` this REVOKES THE SHARE — it
        does not delete the account. Re-running on an already-revoked grant must succeed."""

    @abstractmethod
    async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
        """The current real downstream state, for reconciliation/drift detection."""

    # --- optional, gated by ``capabilities`` ---
    async def widget_data(self, user: ProviderUser) -> WidgetPayload | None:
        """Per-user dashboard data. Scoped to THIS user only — never return another user's data."""
        return None

    def available_grants(self) -> list[GrantTemplate]:
        """Tiers/options the owner can offer for this provider."""
        return []
