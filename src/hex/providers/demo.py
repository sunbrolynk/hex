"""Dev-only demo providers — exercise the lifecycle arc before real providers land (Phase 4).

These are NOT real integrations: ``provision`` always grants, ``status`` always reports present,
``deprovision`` always revokes. Their only job is to populate the ledger so provision → dashboard
is runnable end-to-end in development. ``register_demo_providers`` refuses to wire them when
``env=="production"`` — the demo arc is never a live access surface.
"""

from typing import ClassVar

from hex.config import Settings
from hex.providers.base import Provider
from hex.providers.registry import ProviderRegistry
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
    ProvisionState,
)


class DemoGrant(Grant):
    """Demo providers take no real grant options — any tier accepted, none acted on."""

    tier: str = "standard"


class _DemoProvider(Provider):
    """Shared no-op behaviour; subclasses set the declarations + the deep-link shown on the tile."""

    identity_owner: ClassVar[IdentityOwner] = IdentityOwner.AUTHENTIK
    grant_model: ClassVar[type[Grant]] = DemoGrant
    capabilities: ClassVar[frozenset[Capability]] = frozenset({Capability.AVAILABLE_GRANTS})
    link: ClassVar[str]  # where the tile deep-links (real providers will source this from config)
    # Tiers the owner can offer (key, label). The owner picks a key at invite time; HEx resolves it
    # to the structured grant — no owner-authored grant blobs (ADR 0015).
    tiers: ClassVar[tuple[tuple[str, str], ...]] = (("standard", "Standard"),)

    def available_grants(self) -> list[GrantTemplate]:
        return [
            GrantTemplate(key=key, label=label, grant={"tier": key}) for key, label in self.tiers
        ]

    async def validate_config(self) -> ConfigStatus:
        return ConfigStatus(ok=True)

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        return ProvisionResult(state=ProvisionState.GRANTED, external_ref=f"{self.id}-{user.id}")

    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        return DeprovisionResult(revoked=True)

    async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
        return DownstreamStatus(present=True)


class DemoMediaProvider(_DemoProvider):
    id = "demo-media"
    name = "Demo Media"
    category = "media"
    integration_mode = IntegrationMode.SSO_GROUP
    link = "https://media.demo.hex.local"
    tiers = (("standard", "Standard"), ("premium", "Premium"))


class DemoRequestsProvider(_DemoProvider):
    id = "demo-requests"
    name = "Demo Requests"
    category = "requests"
    integration_mode = IntegrationMode.SSO_GROUP
    link = "https://requests.demo.hex.local"


# Fail-closed allow-list: only an explicitly recognized dev environment may wire the always-grant
# demo providers. Anything else — including a mistyped/non-canonical prod label like "prod" or
# "Production" — is treated as production and refused (non-negotiable #4: never insecure-by-typo).
_DEV_ENVS = frozenset({"dev", "development", "test", "local"})


def register_demo_providers(registry: ProviderRegistry, settings: Settings) -> None:
    """Wire the demo providers when ``dev_providers`` is on. No-op off; refuses outside dev."""
    if not settings.dev_providers:
        return
    if settings.env not in _DEV_ENVS:
        raise RuntimeError(
            f"HEX_DEV_PROVIDERS is only allowed in a development environment, not {settings.env!r}"
        )
    registry.register(DemoMediaProvider())
    registry.register(DemoRequestsProvider())
