"""The Provider ABC: abstractness enforcement, grant schema/parse, optional-method defaults."""

import pytest
from pydantic import ValidationError

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


class _DemoGrant(Grant):
    tier: str = "standard"


class _FakeProvider(Provider):
    id = "fake"
    name = "Fake"
    category = "test"
    integration_mode = IntegrationMode.API_LOCAL
    identity_owner = IdentityOwner.PROVIDER
    grant_model = _DemoGrant

    async def validate_config(self) -> ConfigStatus:
        return ConfigStatus(ok=True)

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        return ProvisionResult(state=ProvisionState.GRANTED, external_ref="ext-1")

    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        return DeprovisionResult(revoked=True)

    async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
        return DownstreamStatus(present=True)


_USER = ProviderUser(id=1, username="u", email=None)


def test_provider_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Provider()  # type: ignore[abstract]


def test_incomplete_provider_cannot_be_instantiated() -> None:
    class _Incomplete(Provider):  # missing the four abstract methods
        id = "x"
        name = "X"
        category = "t"
        integration_mode = IntegrationMode.MANUAL
        identity_owner = IdentityOwner.NONE
        grant_model = _DemoGrant

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_grant_schema_and_parse_round_trip() -> None:
    provider = _FakeProvider()
    assert "tier" in provider.grant_schema()["properties"]
    grant = provider.parse_grant({"tier": "premium"})
    assert isinstance(grant, _DemoGrant)
    assert grant.tier == "premium"


def test_parse_grant_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _FakeProvider().parse_grant({"tier": "x", "nope": 1})


async def test_optional_methods_default_to_noop() -> None:
    provider = _FakeProvider()
    assert await provider.widget_data(_USER) is None
    assert provider.available_grants() == []


async def test_core_methods_callable() -> None:
    provider = _FakeProvider()
    assert (await provider.validate_config()).ok is True
    assert (await provider.provision(_USER, _DemoGrant())).state is ProvisionState.GRANTED
    entry = LedgerEntry(
        user_id=1, provider_id="fake", state=ProvisionState.GRANTED, external_ref="ext-1"
    )
    assert (await provider.deprovision(_USER, entry)).revoked is True
    assert (await provider.status(_USER, entry)).present is True
