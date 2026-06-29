"""Apply an invite's grants across providers, recording the provisioning ledger.

Fail-secure (non-negotiable #6): an uncertain or failed provider call records ``FAILED`` — never a
grant. Each provider is isolated so one failure can't abort the rest. The append-only ledger is the
authoritative record of what was provisioned; deprovision/reconciliation read it back. The engine
does not commit — the caller owns the transaction.
"""

from dataclasses import dataclass
from typing import Any

from hex.database.ledger_manager import LedgerManager
from hex.providers.registry import ProviderRegistry
from hex.providers.types import ProviderUser, ProvisionState


@dataclass(frozen=True)
class ProvisionOutcome:
    provider_id: str
    state: ProvisionState


@dataclass(frozen=True)
class ProvisionSummary:
    """Roll-up of one provisioning run, for the audit summary event (#7)."""

    outcomes: list[ProvisionOutcome]

    @property
    def granted(self) -> int:
        return sum(o.state == ProvisionState.GRANTED for o in self.outcomes)

    @property
    def pending(self) -> int:
        pend = {ProvisionState.PENDING_MANUAL, ProvisionState.PENDING_EXTERNAL_CLAIM}
        return sum(o.state in pend for o in self.outcomes)

    @property
    def failed(self) -> int:
        return sum(o.state == ProvisionState.FAILED for o in self.outcomes)

    def describe(self) -> str:
        return (
            f"granted={self.granted} pending={self.pending} "
            f"partial={self._partial} failed={self.failed}"
        )

    @property
    def _partial(self) -> int:
        return sum(o.state == ProvisionState.PARTIAL for o in self.outcomes)


class ProvisionEngine:
    """Resolve each grant's provider, provision it, and append the outcome to the ledger."""

    def __init__(self, registry: ProviderRegistry, ledger: LedgerManager) -> None:
        self._registry = registry
        self._ledger = ledger

    async def provision_grants(
        self, user: ProviderUser, grants: dict[str, dict[str, Any]]
    ) -> ProvisionSummary:
        outcomes = [
            ProvisionOutcome(provider_id, await self._provision_one(user, provider_id, raw))
            for provider_id, raw in grants.items()
        ]
        return ProvisionSummary(outcomes)

    async def _provision_one(
        self, user: ProviderUser, provider_id: str, raw_grant: dict[str, Any]
    ) -> ProvisionState:
        provider = self._registry.get(provider_id)
        if provider is None:
            return await self._fail(user, provider_id, raw_grant, "unknown provider")
        try:
            grant = provider.parse_grant(raw_grant)
        except Exception:  # noqa: BLE001 — fail-secure: any malformed grant ⇒ FAILED, never grant (#6)
            # Broad on purpose: ``parse_grant`` does ``dict(raw)`` before Pydantic, so a non-mapping
            # value raises TypeError/ValueError (not ValidationError). Catching only ValidationError
            # would let that escape and abort the whole run, breaking per-provider isolation.
            return await self._fail(user, provider_id, raw_grant, "invalid grant")
        try:
            result = await provider.provision(user, grant)
        except Exception as exc:  # noqa: BLE001 — fail-secure: any provider fault ⇒ never grant (#6)
            return await self._fail(
                user, provider_id, raw_grant, f"provider error: {type(exc).__name__}"
            )
        await self._ledger.record_event(
            user_id=user.id,
            provider_id=provider_id,
            state=result.state,
            grant=raw_grant,
            external_ref=result.external_ref,
            detail=result.detail,
            partial=result.partial,
        )
        return result.state

    async def _fail(
        self, user: ProviderUser, provider_id: str, raw_grant: dict[str, Any], detail: str
    ) -> ProvisionState:
        await self._ledger.record_event(
            user_id=user.id,
            provider_id=provider_id,
            state=ProvisionState.FAILED,
            grant=raw_grant,
            detail=detail,
        )
        return ProvisionState.FAILED
