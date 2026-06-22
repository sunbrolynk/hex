"""Startup lifespan: seeds the setup-state row and disposes the engine."""

import logging

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hex.api import main
from hex.api.main import create_app
from hex.database import AuditLogManager, Base, SetupStateManager
from hex.database.models import (
    AuditAction,
    AuditLogEntry,
    AuditResult,
    AuditSeverity,
    SetupPhase,
    SetupState,
)
from hex.setup import hash_token
from tests.conftest import make_settings


async def test_lifespan_initializes_setup_state(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker  # pre-attached → lifespan skips migrate/connect

    async with app.router.lifespan_context(app):
        async with sessionmaker() as session:
            assert await SetupStateManager(session).current_phase() is SetupPhase.FIRST_RUN


async def test_lifespan_mints_and_logs_the_setup_token_once(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    # Assert inside the context: lifespan shutdown disposes the (in-memory) engine.
    with caplog.at_level(logging.WARNING, logger="hex.setup"):
        async with app.router.lifespan_context(app):
            minted = [r for r in caplog.records if "setup token" in r.getMessage().lower()]
            assert len(minted) == 1
            # Logged via a %s arg (out-of-band retrieval); confirm it matches the stored hash.
            token = minted[0].args[-1]  # type: ignore[index]
            assert isinstance(token, str)
            async with sessionmaker() as session:
                state = await session.get(SetupState, 1)
                assert state is not None
                assert state.phase is SetupPhase.FIRST_RUN
                assert state.setup_token_hash == hash_token(token)


async def test_lifespan_audits_token_issuance_in_one_chained_row(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    # Assert inside the context: lifespan shutdown disposes the (in-memory) engine.
    async with app.router.lifespan_context(app):
        async with sessionmaker() as session:
            rows = (await session.execute(select(AuditLogEntry))).scalars().all()
            assert len(rows) == 1
            assert rows[0].action is AuditAction.SETUP_TOKEN_ISSUED
            assert await AuditLogManager(session, app.state.audit_signer).verify_chain() is True


async def test_lifespan_boot_verify_chain_passes_on_clean_chain(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    async with app.router.lifespan_context(app):
        assert app.state.audit_chain_ok is True
        async with sessionmaker() as session:
            rows = (await session.execute(select(AuditLogEntry))).scalars().all()
        # Only the issuance row — a clean verify adds nothing.
        assert [r.action for r in rows] == [AuditAction.SETUP_TOKEN_ISSUED]


async def test_lifespan_boot_verify_chain_detects_tamper_and_boots_anyway(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    # Past FIRST_RUN (no issuance), seed an audit row, then tamper it so verify_chain fails at boot.
    async with sessionmaker() as session:
        state = await SetupStateManager(session).get_or_create()
        state.phase = SetupPhase.COMPLETE
        await AuditLogManager(session, app.state.audit_signer).append(
            action=AuditAction.SETUP_TOKEN_ISSUED,
            severity=AuditSeverity.INFO,
            result=AuditResult.SUCCESS,
            actor="system",
        )
        await session.commit()
        await session.execute(text("UPDATE audit_log SET actor='attacker' WHERE id=1"))
        await session.commit()

    async with app.router.lifespan_context(app):
        assert app.state.audit_chain_ok is False  # warned, not refused
        async with sessionmaker() as session:
            actions = [
                r.action.value
                for r in (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id)))
                .scalars()
                .all()
            ]
    assert "audit.chain.verification_failed" in actions


async def test_lifespan_does_not_mint_token_past_first_run(
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with sessionmaker() as session:
        state = await SetupStateManager(session).get_or_create()
        state.phase = SetupPhase.COMPLETE
        await session.commit()

    app = create_app(make_settings())
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    with caplog.at_level(logging.WARNING, logger="hex.setup"):
        async with app.router.lifespan_context(app):
            pass

    assert not [r for r in caplog.records if "setup token" in r.getMessage().lower()]


async def test_lifespan_production_no_automigrate_asserts_at_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """env=production + auto-migrate off → boot calls the at-head guardrail."""
    db = tmp_path / "guard.db"  # type: ignore[operator]
    async_url = f"sqlite+aiosqlite:///{db}"
    sync = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(sync)
    sync.dispose()

    built = create_async_engine(async_url)
    called: list[bool] = []

    async def fake_assert(_: object) -> None:
        called.append(True)

    monkeypatch.setattr(main, "assert_at_head", fake_assert)
    monkeypatch.setattr(main, "build_engine", lambda _: built)

    app = create_app(make_settings(env="production", db_auto_migrate=False))
    async with app.router.lifespan_context(app):
        assert called == [True]


async def test_lifespan_production_branch_migrates_builds_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """No pre-attached sessionmaker → exercise the real migrate/build/dispose path on SQLite."""
    db = tmp_path / "lifespan.db"  # type: ignore[operator]
    async_url = f"sqlite+aiosqlite:///{db}"

    def fake_migrate(_: object) -> None:
        sync = create_engine(f"sqlite:///{db}")
        Base.metadata.create_all(sync)
        sync.dispose()

    built = create_async_engine(async_url)
    disposed: list[AsyncEngine] = []
    original_dispose = AsyncEngine.dispose

    async def spy_dispose(self: AsyncEngine, close: bool = True) -> None:
        disposed.append(self)
        await original_dispose(self, close)

    monkeypatch.setattr(main, "upgrade_to_head", fake_migrate)
    monkeypatch.setattr(main, "build_engine", lambda _: built)
    monkeypatch.setattr(AsyncEngine, "dispose", spy_dispose)

    app = create_app(make_settings(db_auto_migrate=True))
    assert getattr(app.state, "sessionmaker", None) is None

    async with app.router.lifespan_context(app):
        assert app.state.engine is built
        async with app.state.sessionmaker() as session:
            assert await SetupStateManager(session).current_phase() is SetupPhase.FIRST_RUN

    assert built in disposed  # engine disposed on shutdown
