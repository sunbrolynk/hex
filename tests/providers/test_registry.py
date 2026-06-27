"""ProviderRegistry: register / get / all + duplicate-id protection."""

import pytest

from hex.providers import ProviderRegistry
from hex.providers.base import Provider
from hex.providers.types import (
    ConfigStatus,
    DeprovisionResult,
    DownstreamStatus,
    Grant,
    IdentityOwner,
    IntegrationMode,
    LedgerEntry,
    ProviderUser,
    ProvisionResult,
    ProvisionState,
)


class _Grant(Grant):
    pass


def _provider(provider_id: str) -> Provider:
    class _P(Provider):
        id = provider_id
        name = provider_id
        category = "test"
        integration_mode = IntegrationMode.MANUAL
        identity_owner = IdentityOwner.NONE
        grant_model = _Grant

        async def validate_config(self) -> ConfigStatus:
            return ConfigStatus(ok=True)

        async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
            return ProvisionResult(state=ProvisionState.GRANTED)

        async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
            return DeprovisionResult(revoked=True)

        async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
            return DownstreamStatus(present=False)

    return _P()


def test_register_and_get() -> None:
    registry = ProviderRegistry()
    jellyfin = _provider("jellyfin")
    registry.register(jellyfin)
    assert registry.get("jellyfin") is jellyfin


def test_get_unknown_returns_none() -> None:
    assert ProviderRegistry().get("nope") is None


def test_all_lists_in_registration_order() -> None:
    registry = ProviderRegistry()
    registry.register(_provider("a"))
    registry.register(_provider("b"))
    assert [p.id for p in registry.all()] == ["a", "b"]


def test_duplicate_id_raises() -> None:
    registry = ProviderRegistry()
    registry.register(_provider("dup"))
    with pytest.raises(ValueError, match="duplicate provider id"):
        registry.register(_provider("dup"))


def test_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="empty provider id"):
        ProviderRegistry().register(_provider(""))


def test_missing_declaration_rejected() -> None:
    # A concrete provider (all abstract methods implemented) that forgot grant_model must fail
    # loudly at registration, not silently at first use.
    class _Bare(Provider):
        id = "bare"
        name = "Bare"
        category = "test"
        integration_mode = IntegrationMode.MANUAL
        identity_owner = IdentityOwner.NONE
        # grant_model intentionally not set

        async def validate_config(self) -> ConfigStatus:
            return ConfigStatus(ok=True)

        async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
            return ProvisionResult(state=ProvisionState.GRANTED)

        async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
            return DeprovisionResult(revoked=True)

        async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
            return DownstreamStatus(present=False)

    with pytest.raises(ValueError, match="missing provider declarations"):
        ProviderRegistry().register(_Bare())
