"""The provider contract: one interface (``Provider``), four integration modes, two axes."""

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
    WidgetPayload,
)

__all__ = [
    "Capability",
    "ConfigStatus",
    "DeprovisionResult",
    "DownstreamStatus",
    "Grant",
    "GrantTemplate",
    "IdentityOwner",
    "IntegrationMode",
    "LedgerEntry",
    "Provider",
    "ProviderRegistry",
    "ProvisionResult",
    "ProvisionState",
    "ProviderUser",
    "WidgetPayload",
]
