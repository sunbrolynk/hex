"""The conformance suite, run against the in-memory reference providers (both identity owners)."""

import pytest

from hex.providers.types import (
    DeprovisionResult,
    LedgerEntry,
    ProviderUser,
    ProvisionState,
    WidgetPayload,
)

from .conformance import (
    assert_capability_method_consistency,
    assert_deprovision_idempotent_and_correct,
    assert_no_cross_user_leak,
    run_conformance,
)
from .reference import ReferenceExternalProvider, ReferenceGrant, ReferenceLocalProvider

# Distinct, non-substring ids + PII so the cross-user-leak check can't false-pass.
_USER = ProviderUser(id=1001, username="alice", email="alice@example.test")
_OTHER = ProviderUser(id=2002, username="bob", email="bob@example.test")


async def test_local_reference_conforms() -> None:
    await run_conformance(
        healthy=ReferenceLocalProvider(),
        failing=ReferenceLocalProvider(healthy=False),
        misconfigured=ReferenceLocalProvider(valid_config=False),
        user=_USER,
        other_user=_OTHER,
        grant=ReferenceGrant(),
    )


async def test_external_reference_conforms() -> None:
    healthy = ReferenceExternalProvider()
    await run_conformance(
        healthy=healthy,
        failing=ReferenceExternalProvider(healthy=False),
        misconfigured=ReferenceExternalProvider(valid_config=False),
        user=_USER,
        other_user=_OTHER,
        grant=ReferenceGrant(),
        account_survives=healthy.account_exists,
    )


async def test_external_deprovision_revokes_share_but_keeps_account() -> None:
    # The asymmetry the two-axis model exists for, asserted directly: after deprovision the share is
    # gone but the external account remains (HEx cannot delete it).
    provider = ReferenceExternalProvider()
    await assert_deprovision_idempotent_and_correct(
        provider, _USER, ReferenceGrant(), account_survives=provider.account_exists
    )
    entry = LedgerEntry(
        user_id=_USER.id, provider_id=provider.id, state=ProvisionState.REVOKED, external_ref=None
    )
    status = await provider.status(_USER, entry)
    assert status.present is False  # share revoked
    assert provider.account_exists(_USER) is True  # account kept


def test_capability_consistency_on_both_references() -> None:
    # Local declares WIDGET_DATA and overrides it; external declares neither and overrides neither.
    assert_capability_method_consistency(ReferenceLocalProvider())
    assert_capability_method_consistency(ReferenceExternalProvider())


# --- Meta-tests: the harness must REJECT a non-conformant provider, or it isn't a gate. ---


class _NoOpDeprovisionProvider(ReferenceLocalProvider):
    """Claims success but removes nothing — the silent-offboarding bug."""

    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        return DeprovisionResult(revoked=True)  # lies: the user is still provisioned


class _LeakyProvider(ReferenceLocalProvider):
    """Returns every user's data in one payload — a cross-user leak."""

    async def widget_data(self, user: ProviderUser) -> WidgetPayload:
        return WidgetPayload(data={"all_users": dict(self._users)})


async def test_harness_rejects_noop_deprovision() -> None:
    with pytest.raises(AssertionError, match="still present downstream"):
        await assert_deprovision_idempotent_and_correct(
            _NoOpDeprovisionProvider(), _USER, ReferenceGrant()
        )


async def test_harness_rejects_cross_user_leak() -> None:
    with pytest.raises(AssertionError, match="leaked another user"):
        await assert_no_cross_user_leak(_LeakyProvider(), _USER, _OTHER, ReferenceGrant())
