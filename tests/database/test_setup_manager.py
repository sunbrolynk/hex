"""SetupStateManager: singleton lifecycle + token-gated bootstrap entry."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hex.database import SetupStateManager
from hex.database.models import SetupPhase, SetupState
from hex.setup import hash_token


async def test_get_or_create_is_idempotent(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)

    first = await manager.get_or_create()
    assert first.id == 1
    assert first.phase is SetupPhase.FIRST_RUN

    again = await manager.get_or_create()
    assert again.id == 1

    count = await db_session.scalar(select(func.count()).select_from(SetupState))
    assert count == 1


async def test_current_phase_defaults_first_run_before_init(db_session: AsyncSession) -> None:
    assert await SetupStateManager(db_session).current_phase() is SetupPhase.FIRST_RUN


async def test_is_first_run_until_complete(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.get_or_create()
    assert await manager.is_first_run() is True

    state = await db_session.get(SetupState, 1)
    assert state is not None
    state.phase = SetupPhase.COMPLETE
    await db_session.commit()

    assert await manager.is_first_run() is False


async def test_issue_setup_token_stores_only_the_hash(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash == hash_token(token)
    assert state.setup_token_hash != token  # plaintext is never persisted
    assert state.setup_token_issued_at is not None


async def test_issue_setup_token_remints_each_call(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    first = await manager.issue_setup_token()
    second = await manager.issue_setup_token()
    assert first != second  # a fresh boot invalidates the prior token


async def test_issue_setup_token_returns_none_past_first_run(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    state = await manager.get_or_create()
    state.phase = SetupPhase.BOOTSTRAP
    await db_session.commit()

    assert await manager.issue_setup_token() is None


async def test_begin_bootstrap_advances_on_correct_token(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None

    assert await manager.begin_bootstrap(token) is True
    assert await manager.current_phase() is SetupPhase.BOOTSTRAP

    state = await db_session.get(SetupState, 1)
    assert state is not None
    assert state.setup_token_hash is None  # single-use: consumed on success


async def test_begin_bootstrap_rejects_wrong_token(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.issue_setup_token()

    assert await manager.begin_bootstrap("not-the-token") is False
    assert await manager.current_phase() is SetupPhase.FIRST_RUN  # no state change


async def test_begin_bootstrap_rejects_when_no_token_issued(db_session: AsyncSession) -> None:
    manager = SetupStateManager(db_session)
    await manager.get_or_create()  # FIRST_RUN but no token minted

    assert await manager.begin_bootstrap("anything") is False
    assert await manager.current_phase() is SetupPhase.FIRST_RUN


async def test_begin_bootstrap_is_completion_bound(db_session: AsyncSession) -> None:
    """Once setup has advanced, the token can never be replayed to re-claim ownership."""
    manager = SetupStateManager(db_session)
    token = await manager.issue_setup_token()
    assert token is not None
    assert await manager.begin_bootstrap(token) is True

    # A replay of the same token after advancing must not move the phase.
    assert await manager.begin_bootstrap(token) is False
    assert await manager.current_phase() is SetupPhase.BOOTSTRAP


async def test_begin_bootstrap_is_single_use_across_sessions(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Two valid-token unlocks (separate sessions) yield exactly one success — the atomic burn."""
    async with sessionmaker() as setup_session:
        token = await SetupStateManager(setup_session).issue_setup_token()
    assert token is not None

    async with sessionmaker() as s1, sessionmaker() as s2:
        first = await SetupStateManager(s1).begin_bootstrap(token)
        second = await SetupStateManager(s2).begin_bootstrap(token)
    assert sorted([first, second]) == [False, True]
