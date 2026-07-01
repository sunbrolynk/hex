"""In-memory reference providers — test artifacts (not shipped) that exercise the conformance suite.

Two shapes prove the deprovision asymmetry the two-axis model exists for: a provider-owned identity
(``identity_owner=provider`` — deprovision deletes, symmetric) and an external identity
(``identity_owner=external`` — deprovision revokes the share but cannot delete the account).
Each takes ``healthy``/``valid_config`` toggles so the harness can drive the failure paths.
"""

from typing import Any

from hex.providers.base import Provider
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


class ReferenceGrant(Grant):
    tier: str = "standard"


class ReferenceLocalProvider(Provider):
    """``api_local`` / ``provider`` — HEx owns the downstream user; deprovision deletes it."""

    id = "ref-local"
    name = "Reference (local)"
    category = "test"
    integration_mode = IntegrationMode.API_LOCAL
    identity_owner = IdentityOwner.PROVIDER
    capabilities = frozenset({Capability.WIDGET_DATA, Capability.AVAILABLE_GRANTS})
    grant_model = ReferenceGrant

    def __init__(self, *, healthy: bool = True, valid_config: bool = True) -> None:
        self._healthy = healthy
        self._valid_config = valid_config
        self._users: dict[int, dict[str, Any]] = {}

    async def validate_config(self) -> ConfigStatus:
        return ConfigStatus(
            ok=self._valid_config, detail=None if self._valid_config else "bad creds"
        )

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        if not self._healthy:
            return ProvisionResult(state=ProvisionState.FAILED, detail="downstream uncertain")
        ref = f"local-{user.id}"
        self._users[user.id] = {"ref": ref, "grant": grant.model_dump()}  # idempotent upsert
        return ProvisionResult(state=ProvisionState.GRANTED, external_ref=ref)

    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        self._users.pop(user.id, None)  # symmetric delete; idempotent
        return DeprovisionResult(revoked=True)

    async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
        return DownstreamStatus(present=user.id in self._users)

    async def widget_data(self, user: ProviderUser) -> WidgetPayload | None:
        record = self._users.get(user.id)
        if record is None:
            return None
        return WidgetPayload(data={"user_id": user.id, "ref": record["ref"]})  # this user only

    def available_grants(self) -> list[GrantTemplate]:
        return [
            GrantTemplate(key="standard", label="Standard", grant={"tier": "standard"}),
            GrantTemplate(
                key="premium", label="Premium", grant={"tier": "premium"}, description="Full access"
            ),
        ]


class ReferenceExternalProvider(Provider):
    """``external_invite`` / ``external`` — identity is off-box; deprovision revokes the share."""

    id = "ref-external"
    name = "Reference (external)"
    category = "test"
    integration_mode = IntegrationMode.EXTERNAL_INVITE
    identity_owner = IdentityOwner.EXTERNAL
    grant_model = ReferenceGrant

    def __init__(self, *, healthy: bool = True, valid_config: bool = True) -> None:
        self._healthy = healthy
        self._valid_config = valid_config
        self._accounts: set[int] = set()  # external accounts HEx cannot delete
        self._shares: dict[int, str] = {}  # active shares HEx can revoke

    async def validate_config(self) -> ConfigStatus:
        return ConfigStatus(
            ok=self._valid_config, detail=None if self._valid_config else "bad creds"
        )

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        if not self._healthy:
            return ProvisionResult(state=ProvisionState.FAILED, detail="downstream uncertain")
        self._accounts.add(user.id)  # the external account exists (created/linked off-box)
        ref = f"share-{user.id}"
        self._shares[user.id] = ref  # idempotent
        return ProvisionResult(state=ProvisionState.GRANTED, external_ref=ref)

    async def deprovision(self, user: ProviderUser, entry: LedgerEntry) -> DeprovisionResult:
        self._shares.pop(user.id, None)  # revoke the SHARE only — never delete the account
        return DeprovisionResult(revoked=True)

    async def status(self, user: ProviderUser, entry: LedgerEntry) -> DownstreamStatus:
        return DownstreamStatus(present=user.id in self._shares)

    def account_exists(self, user: ProviderUser) -> bool:
        """Test hook: the external account persists even after its share is revoked."""
        return user.id in self._accounts
