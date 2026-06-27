"""Provider-contract value types: the frozen vocabulary + structured-grant validation."""

import pytest
from pydantic import ValidationError

from hex.providers.types import (
    DeprovisionResult,
    Grant,
    IdentityOwner,
    IntegrationMode,
    ProvisionResult,
    ProvisionState,
)


def test_integration_modes_are_exactly_the_four() -> None:
    assert {m.value for m in IntegrationMode} == {
        "sso_group",
        "api_local",
        "external_invite",
        "manual",
    }


def test_identity_owners_are_exactly_the_four() -> None:
    assert {o.value for o in IdentityOwner} == {"authentik", "provider", "external", "none"}


def test_provision_states() -> None:
    assert {s.value for s in ProvisionState} == {
        "granted",
        "pending_manual",
        "pending_external_claim",
        "partial",
        "failed",
        "revoked",
    }


class _DemoGrant(Grant):
    libraries: list[str]
    max_sessions: int = 2


def test_grant_validates_input() -> None:
    grant = _DemoGrant.model_validate({"libraries": ["movies"], "max_sessions": 3})
    assert grant.libraries == ["movies"]
    assert grant.max_sessions == 3


def test_grant_rejects_unknown_fields() -> None:
    # extra="forbid" on the base — never accept an unvalidated/extraneous grant blob.
    with pytest.raises(ValidationError):
        _DemoGrant.model_validate({"libraries": ["m"], "bogus": 1})


def test_grant_schema_is_json_schema() -> None:
    schema = _DemoGrant.model_json_schema()
    assert schema["properties"].keys() >= {"libraries", "max_sessions"}
    assert "libraries" in schema["required"]  # no default → required


def test_results_require_explicit_state_no_optimistic_default() -> None:
    # Fail-secure guard: a result must never be constructible without stating its outcome, so nobody
    # can later add an optimistic default (e.g. state=GRANTED) and silently break provisioning.
    with pytest.raises(TypeError):
        ProvisionResult()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        DeprovisionResult()  # type: ignore[call-arg]
