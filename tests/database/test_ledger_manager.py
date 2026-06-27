"""Provisioning ledger: append events, derive current state, and the active-entry projection."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import LedgerManager, User
from hex.providers.types import ProvisionState


async def _user(session: AsyncSession, sub: str = "sub-1") -> User:
    user = User(authentik_sub=sub, username="u")
    session.add(user)
    await session.flush()
    return user


async def test_record_and_current_entry(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    manager = LedgerManager(db_session)
    await manager.record_event(
        user_id=user.id,
        provider_id="jellyfin",
        state=ProvisionState.GRANTED,
        grant={"libraries": ["movies"]},
        external_ref="jf-1",
    )
    entry = await manager.current_entry(user.id, "jellyfin")
    assert entry is not None
    assert entry.user_id == user.id
    assert entry.state is ProvisionState.GRANTED
    assert entry.external_ref == "jf-1"
    assert entry.grant == {"libraries": ["movies"]}


async def test_current_entry_reflects_latest_event(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    manager = LedgerManager(db_session)
    await manager.record_event(
        user_id=user.id, provider_id="jellyfin", state=ProvisionState.GRANTED
    )
    await manager.record_event(
        user_id=user.id, provider_id="jellyfin", state=ProvisionState.REVOKED
    )
    entry = await manager.current_entry(user.id, "jellyfin")
    assert entry is not None
    assert entry.state is ProvisionState.REVOKED  # latest event wins (derived current state)


async def test_current_entry_none_when_no_events(db_session: AsyncSession) -> None:
    assert await LedgerManager(db_session).current_entry(999, "nope") is None


async def test_history_is_oldest_first(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    manager = LedgerManager(db_session)
    await manager.record_event(user_id=user.id, provider_id="p", state=ProvisionState.GRANTED)
    await manager.record_event(user_id=user.id, provider_id="p", state=ProvisionState.PARTIAL)
    assert [e.state for e in await manager.history(user.id, "p")] == [
        ProvisionState.GRANTED,
        ProvisionState.PARTIAL,
    ]


async def test_active_entries_excludes_revoked_and_failed(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    manager = LedgerManager(db_session)
    await manager.record_event(user_id=user.id, provider_id="active", state=ProvisionState.GRANTED)
    await manager.record_event(user_id=user.id, provider_id="gone", state=ProvisionState.GRANTED)
    await manager.record_event(user_id=user.id, provider_id="gone", state=ProvisionState.REVOKED)
    await manager.record_event(user_id=user.id, provider_id="bad", state=ProvisionState.FAILED)

    pairs = {(e.user_id, e.provider_id) for e in await manager.active_entries()}
    assert (user.id, "active") in pairs
    assert (user.id, "gone") not in pairs  # latest event REVOKED → not active
    assert (user.id, "bad") not in pairs  # FAILED → not active


async def test_partial_record_is_persisted(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    event = await LedgerManager(db_session).record_event(
        user_id=user.id,
        provider_id="p",
        state=ProvisionState.PARTIAL,
        partial={"steps_done": ["a"]},
    )
    assert event.partial == {"steps_done": ["a"]}
    assert event.id is not None


async def test_append_only_trigger_blocks_update_and_delete(db_session: AsyncSession) -> None:
    """Migration 0009's SQLite immutability trigger rejects UPDATE/DELETE — append-only is the
    ledger's core guarantee (the Postgres equivalent is covered by the migration round-trip)."""
    user = await _user(db_session)
    await LedgerManager(db_session).record_event(
        user_id=user.id, provider_id="p", state=ProvisionState.GRANTED
    )
    # Apply the exact SQLite triggers migration 0009 installs (the fast-suite schema is built from
    # metadata, which carries no triggers), then prove history can't be rewritten.
    for ddl in (
        "CREATE TRIGGER hex_provisioning_events_no_update BEFORE UPDATE ON provisioning_events "
        "BEGIN SELECT RAISE(ABORT, 'provisioning_events is append-only'); END;",
        "CREATE TRIGGER hex_provisioning_events_no_delete BEFORE DELETE ON provisioning_events "
        "BEGIN SELECT RAISE(ABORT, 'provisioning_events is append-only'); END;",
    ):
        await db_session.execute(text(ddl))
    await db_session.commit()

    with pytest.raises(DBAPIError):
        await db_session.execute(text("UPDATE provisioning_events SET provider_id = 'x'"))
    await db_session.rollback()
    with pytest.raises(DBAPIError):
        await db_session.execute(text("DELETE FROM provisioning_events"))
    await db_session.rollback()
