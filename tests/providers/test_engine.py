"""ProvisionEngine: per-grant provider resolution, fail-secure outcomes, and ledger recording."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hex.database import LedgerManager, User
from hex.providers import Grant, ProviderRegistry, ProviderUser, ProvisionState
from hex.providers.engine import ProvisionEngine
from hex.providers.types import ProvisionResult
from tests.providers.reference import ReferenceLocalProvider


class _BoomProvider(ReferenceLocalProvider):
    """A provider whose provision raises — the engine must treat this fail-secure."""

    id = "ref-boom"

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        raise RuntimeError("kaboom")


class _PartialProvider(ReferenceLocalProvider):
    id = "ref-partial"

    async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
        return ProvisionResult(
            state=ProvisionState.PARTIAL, external_ref="p", partial={"did": ["step-a"]}
        )


class _SecondProvider(ReferenceLocalProvider):
    """A second healthy provider, for isolation tests that need two distinct ids."""

    id = "ref-second"


async def _seed_user(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        user = User(authentik_sub="sub", username="u", email="u@e.test")
        session.add(user)
        await session.flush()
        uid = user.id
        await session.commit()
    return uid


def _registry(*providers: ReferenceLocalProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    return registry


async def _run(
    sessionmaker: async_sessionmaker[AsyncSession],
    registry: ProviderRegistry,
    uid: int,
    grants: dict[str, Any],
) -> tuple[Any, AsyncSession]:
    session = sessionmaker()
    engine = ProvisionEngine(registry, LedgerManager(session))
    summary = await engine.provision_grants(ProviderUser(uid, "u", "u@e.test"), grants)
    await session.commit()
    return summary, session


async def test_healthy_grant_records_granted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=True))
    summary, session = await _run(sessionmaker, registry, uid, {"ref-local": {"tier": "premium"}})
    async with session:
        assert (summary.granted, summary.failed) == (1, 0)
        entry = await LedgerManager(session).current_entry(uid, "ref-local")
        assert entry is not None
        assert entry.state == ProvisionState.GRANTED
        assert entry.grant == {"tier": "premium"}


async def test_provider_failed_result_records_failed(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=False))  # provision returns FAILED
    summary, session = await _run(sessionmaker, registry, uid, {"ref-local": {}})
    async with session:
        assert summary.failed == 1
        entry = await LedgerManager(session).current_entry(uid, "ref-local")
        assert entry is not None and entry.state == ProvisionState.FAILED


async def test_unknown_provider_is_failed(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    summary, session = await _run(sessionmaker, _registry(), uid, {"nope": {}})
    async with session:
        assert summary.failed == 1
        entry = await LedgerManager(session).current_entry(uid, "nope")
        assert entry is not None and entry.state == ProvisionState.FAILED


async def test_invalid_grant_is_failed_not_provisioned(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=True))
    # extra=forbid on the grant model → the bogus field fails validation, never reaches provision.
    summary, session = await _run(sessionmaker, registry, uid, {"ref-local": {"bogus": 1}})
    async with session:
        assert summary.failed == 1
        entry = await LedgerManager(session).current_entry(uid, "ref-local")
        assert entry is not None and entry.state == ProvisionState.FAILED


async def test_provider_exception_is_failed_secure(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    summary, session = await _run(sessionmaker, _registry(_BoomProvider()), uid, {"ref-boom": {}})
    async with session:
        # #6: a provider fault must record FAILED, never a grant.
        assert summary.failed == 1 and summary.granted == 0
        entry = await LedgerManager(session).current_entry(uid, "ref-boom")
        assert entry is not None and entry.state == ProvisionState.FAILED


async def test_partial_state_is_recorded(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    summary, session = await _run(
        sessionmaker, _registry(_PartialProvider()), uid, {"ref-partial": {}}
    )
    async with session:
        # The roll-up must count the partial (not as granted/failed), and surface it in describe().
        assert (summary.granted, summary.failed, summary.pending) == (0, 0, 0)
        assert "partial=1" in summary.describe()
        entry = await LedgerManager(session).current_entry(uid, "ref-partial")
        assert entry is not None and entry.state == ProvisionState.PARTIAL


@pytest.mark.parametrize(
    "state", [ProvisionState.PENDING_MANUAL, ProvisionState.PENDING_EXTERNAL_CLAIM]
)
async def test_pending_state_counts_and_is_recorded(
    sessionmaker: async_sessionmaker[AsyncSession], state: ProvisionState
) -> None:
    class _Pending(ReferenceLocalProvider):
        id = "ref-pending"

        async def provision(self, user: ProviderUser, grant: Grant) -> ProvisionResult:
            return ProvisionResult(state=state, external_ref="pend")

    uid = await _seed_user(sessionmaker)
    summary, session = await _run(sessionmaker, _registry(_Pending()), uid, {"ref-pending": {}})
    async with session:
        # Both PENDING states roll into the pending bucket and are written to the ledger as-is.
        assert (summary.pending, summary.granted, summary.failed) == (1, 0, 0)
        assert "pending=1" in summary.describe()
        entry = await LedgerManager(session).current_entry(uid, "ref-pending")
        assert entry is not None and entry.state == state


@pytest.mark.parametrize("bad_value", [None, 5, "not-a-mapping"])
async def test_non_mapping_grant_is_failed_secure(
    sessionmaker: async_sessionmaker[AsyncSession], bad_value: Any
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=True))
    # ``parse_grant`` does ``dict(raw)`` before Pydantic: a non-mapping value raises TypeError/
    # ValueError, not ValidationError. The engine must still record FAILED, never let it escape.
    grants: dict[str, Any] = {"ref-local": bad_value}
    summary, session = await _run(sessionmaker, registry, uid, grants)
    async with session:
        assert summary.failed == 1 and summary.granted == 0
        entry = await LedgerManager(session).current_entry(uid, "ref-local")
        assert entry is not None and entry.state == ProvisionState.FAILED


async def test_malformed_grant_does_not_abort_the_rest(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=True), _SecondProvider())
    # A non-mapping grant for one provider must not abort provisioning of the others (isolation).
    grants: dict[str, Any] = {"ref-local": {"tier": "x"}, "ref-second": None}
    summary, session = await _run(sessionmaker, registry, uid, grants)
    async with session:
        assert (summary.granted, summary.failed) == (1, 1)
        ledger = LedgerManager(session)
        good = await ledger.current_entry(uid, "ref-local")
        bad = await ledger.current_entry(uid, "ref-second")
        assert good is not None and good.state == ProvisionState.GRANTED
        assert bad is not None and bad.state == ProvisionState.FAILED


async def test_one_failure_does_not_abort_the_rest(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _seed_user(sessionmaker)
    registry = _registry(ReferenceLocalProvider(healthy=True), _BoomProvider())
    summary, session = await _run(
        sessionmaker, registry, uid, {"ref-local": {"tier": "x"}, "ref-boom": {}}
    )
    async with session:
        # Each provider is isolated: one granted, one failed, both recorded.
        assert (summary.granted, summary.failed) == (1, 1)
        ledger = LedgerManager(session)
        local = await ledger.current_entry(uid, "ref-local")
        boom = await ledger.current_entry(uid, "ref-boom")
        assert local is not None and local.state == ProvisionState.GRANTED
        assert boom is not None and boom.state == ProvisionState.FAILED
        assert "granted=1" in summary.describe() and "failed=1" in summary.describe()
