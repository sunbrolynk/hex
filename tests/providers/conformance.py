"""Reusable provider-contract conformance suite (docs/PROVIDER_CONTRACT.md, docs/TESTING.md).

Every provider's test composes these to prove the contract invariants: fail-closed config,
idempotent + fail-secure provision, idempotent deprovision with the correct ``identity_owner``
(``external`` revokes the share, never deletes the account), no cross-user data leak, and that
declared capabilities match overridden methods. A provider that fails any of these does not ship.
"""

from collections.abc import Callable

from hex.providers.base import Provider
from hex.providers.types import (
    Capability,
    Grant,
    IdentityOwner,
    LedgerEntry,
    ProviderUser,
    ProvisionState,
)


def _entry(
    provider: Provider, user: ProviderUser, external_ref: str | None, grant: Grant
) -> LedgerEntry:
    return LedgerEntry(
        user_id=user.id,
        provider_id=provider.id,
        state=ProvisionState.GRANTED,
        external_ref=external_ref,
        grant=grant.model_dump(),
    )


def assert_capability_method_consistency(provider: Provider) -> None:
    """A declared capability must have its method overridden, and an undeclared one must not."""
    cls = type(provider)
    assert (Capability.WIDGET_DATA in provider.capabilities) == (
        cls.widget_data is not Provider.widget_data
    ), "WIDGET_DATA capability must match whether widget_data is overridden"
    assert (Capability.AVAILABLE_GRANTS in provider.capabilities) == (
        cls.available_grants is not Provider.available_grants
    ), "AVAILABLE_GRANTS capability must match whether available_grants is overridden"


async def assert_validate_config_fails_closed(misconfigured: Provider) -> None:
    status = await misconfigured.validate_config()
    assert status.ok is False, "a misconfigured provider must report validate_config().ok is False"


async def assert_provision_fails_secure(
    failing: Provider, user: ProviderUser, grant: Grant
) -> None:
    result = await failing.provision(user, grant)
    assert result.state is ProvisionState.FAILED, (
        "an uncertain downstream must yield FAILED, never optimistic success"
    )


async def assert_provision_idempotent(provider: Provider, user: ProviderUser, grant: Grant) -> None:
    first = await provider.provision(user, grant)
    second = await provider.provision(user, grant)
    assert first.state is not ProvisionState.FAILED, "a healthy provision must not return FAILED"
    assert (first.state, first.external_ref) == (second.state, second.external_ref), (
        "provision must be idempotent — re-running yields the same state and external_ref"
    )


def _assert_user_absent(data: dict[str, object], user: ProviderUser) -> None:
    """No identifier of ``user`` (id, username, email) may appear in another user's payload."""
    rendered = repr(data)
    for token in (str(user.id), user.username, user.email):
        if token:
            assert token not in rendered, f"payload leaked another user's data: {token!r}"


async def assert_no_cross_user_leak(
    provider: Provider, user: ProviderUser, other: ProviderUser, grant: Grant
) -> None:
    """widget_data/status must be scoped to the requested user — no other user's data, both ways."""
    assert user.id != other.id, "the leak check needs two distinct users to be meaningful"
    await provider.provision(user, grant)
    await provider.provision(other, grant)
    if Capability.WIDGET_DATA in provider.capabilities:
        payload_user = await provider.widget_data(user)
        payload_other = await provider.widget_data(other)
        assert payload_user is not None and payload_other is not None
        # Both directions: catches a provider hardwired to one user's data. Identity covers id +
        # PII (username/email), so leaked profile fields are caught, not just the numeric id.
        _assert_user_absent(payload_user.data, other)
        _assert_user_absent(payload_other.data, user)
    # status must reflect the per-user entry, not a global yes: a never-provisioned user is absent.
    ghost = ProviderUser(id=999_999, username="ghost-user", email="ghost@example.test")
    ghost_status = await provider.status(ghost, _entry(provider, ghost, None, grant))
    assert ghost_status.present is False, "status must be per-user, not unconditionally present"


async def assert_deprovision_idempotent_and_correct(
    provider: Provider,
    user: ProviderUser,
    grant: Grant,
    *,
    account_survives: Callable[[ProviderUser], bool] | None = None,
) -> None:
    result = await provider.provision(user, grant)
    entry = _entry(provider, user, result.external_ref, grant)
    first = await provider.deprovision(user, entry)
    second = await provider.deprovision(user, entry)
    assert first.revoked and second.revoked, (
        "deprovision must be idempotent — already-revoked returns revoked=True, not an error"
    )
    # The access must actually be gone downstream — a no-op deprovision that merely reports
    # revoked=True is the silent-offboarding failure the whole contract exists to prevent (#6).
    post = await provider.status(user, entry)
    assert post.present is False, (
        "deprovision reported success but access is still present downstream"
    )
    if provider.identity_owner is IdentityOwner.EXTERNAL:
        assert account_survives is not None, (
            "an external provider must supply an account_survives hook"
        )
        assert account_survives(user) is True, (
            "external deprovision must revoke the share, never delete the account"
        )


async def run_conformance(
    *,
    healthy: Provider,
    failing: Provider,
    misconfigured: Provider,
    user: ProviderUser,
    other_user: ProviderUser,
    grant: Grant,
    account_survives: Callable[[ProviderUser], bool] | None = None,
) -> None:
    """Run the full conformance suite against a provider and its failing/misconfigured variants."""
    assert_capability_method_consistency(healthy)
    await assert_validate_config_fails_closed(misconfigured)
    await assert_provision_fails_secure(failing, user, grant)
    await assert_provision_idempotent(healthy, user, grant)
    await assert_no_cross_user_leak(healthy, user, other_user, grant)
    await assert_deprovision_idempotent_and_correct(
        healthy, user, grant, account_survives=account_survives
    )
