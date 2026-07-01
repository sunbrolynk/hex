"""Dev-only demo providers + their hard prod-off registration gate."""

import pytest

from hex.api.main import create_app
from hex.providers import ProviderRegistry, ProvisionState
from hex.providers.demo import (
    DemoGrant,
    DemoMediaProvider,
    register_demo_providers,
)
from hex.providers.types import LedgerEntry, ProviderUser
from tests.conftest import make_settings

_USER = ProviderUser(id=7, username="u", email="u@example.test")
_ENTRY = LedgerEntry(
    user_id=7, provider_id="demo-media", state=ProvisionState.GRANTED, external_ref=None
)


async def test_demo_provider_always_grants_and_is_present() -> None:
    provider = DemoMediaProvider()
    assert (await provider.validate_config()).ok
    result = await provider.provision(_USER, DemoGrant())
    assert result.state is ProvisionState.GRANTED
    assert result.external_ref == "demo-media-7"
    assert (await provider.status(_USER, _ENTRY)).present
    assert (await provider.deprovision(_USER, _ENTRY)).revoked


def test_demo_media_offers_tiers() -> None:
    tiers = DemoMediaProvider().available_grants()
    assert {t.key for t in tiers} == {"standard", "premium"}
    # A tier resolves to the provider's structured grant (what the invite stores).
    assert next(t for t in tiers if t.key == "premium").grant == {"tier": "premium"}


def test_register_demo_providers_off_by_default() -> None:
    registry = ProviderRegistry()
    register_demo_providers(registry, make_settings())
    assert registry.all() == []


def test_register_demo_providers_wires_tiles_in_dev() -> None:
    registry = ProviderRegistry()
    register_demo_providers(registry, make_settings(env="dev", dev_providers=True))
    assert {p.id for p in registry.all()} == {"demo-media", "demo-requests"}


def test_register_demo_providers_refuses_in_production() -> None:
    registry = ProviderRegistry()
    with pytest.raises(RuntimeError, match="only allowed in a development"):
        register_demo_providers(registry, make_settings(env="production", dev_providers=True))
    assert registry.all() == []  # nothing wired before the refusal


@pytest.mark.parametrize("label", ["prod", "Production", "staging", "production "])
def test_register_demo_providers_refuses_non_canonical_prod_labels(label: str) -> None:
    # Fail-closed: a mistyped/non-canonical env must NOT read as "not production" and wire demos.
    registry = ProviderRegistry()
    with pytest.raises(RuntimeError, match="only allowed in a development"):
        register_demo_providers(registry, make_settings(env=label, dev_providers=True))
    assert registry.all() == []


def test_create_app_refuses_to_boot_with_dev_providers_in_production() -> None:
    # The app-factory promise (config.py / main.py): dev providers + env=production aborts startup.
    with pytest.raises(RuntimeError, match="only allowed in a development"):
        create_app(make_settings(env="production", dev_providers=True))
