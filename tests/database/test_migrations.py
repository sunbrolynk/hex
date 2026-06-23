"""Alembic migration round-trip against real Postgres (CI pg job only).

Environment-gated, not skipped-to-be-green: the CI Postgres job sets HEX_RUN_PG_TESTS=1
(plus HEX_DB_*) so these run there. SQLite tests build schema from metadata instead.
"""

import asyncio
import os

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from hex.config import Settings
from hex.database.migrate import build_config

pytestmark = pytest.mark.skipif(
    not os.environ.get("HEX_RUN_PG_TESTS"),
    reason="needs Postgres; runs in the CI pg job (HEX_RUN_PG_TESTS=1)",
)


async def _assert_setup_state_queryable(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # Name the 0002 columns explicitly so a no-op add-column migration would fail here.
            await conn.execute(
                text("SELECT id, phase, setup_token_hash, setup_token_issued_at FROM setup_state")
            )
    finally:
        await engine.dispose()


async def _assert_audit_schema(url: str) -> None:
    """0003 built the audit tables AND the integrity constraints the hash chain relies on."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # Named columns → a missing/renamed audit column fails here, not silently in CI.
            await conn.execute(
                text(
                    "SELECT id, occurred_at, action, severity, result, actor, target, meta, "
                    "prev_hash, entry_hash FROM audit_log"
                )
            )
            await conn.execute(text("SELECT id, last_hash, seq FROM audit_chain_head"))
            # The unique (anti-fork) and singleton constraints must be in the catalog, not just
            # the ORM metadata — a migration that dropped them would otherwise ship green.
            result = await conn.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname IN "
                    "('uq_audit_log_entry_hash', 'ck_audit_chain_head_singleton')"
                )
            )
            assert {row[0] for row in result} == {
                "uq_audit_log_entry_hash",
                "ck_audit_chain_head_singleton",
            }
    finally:
        await engine.dispose()


async def _assert_auth_schema(url: str) -> None:
    """0004 built the users / sessions / login-state tables (named columns catch drift)."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "SELECT id, authentik_sub, username, email, is_owner, created_at, updated_at "
                    "FROM users"
                )
            )
            await conn.execute(
                text(
                    "SELECT session_token_hash, user_id, created_at, expires_at, last_seen_at "
                    "FROM user_sessions"
                )
            )
            await conn.execute(
                text(
                    "SELECT state_hash, nonce, code_verifier, redirect_to, created_at, expires_at "
                    "FROM oidc_login_state"
                )
            )
    finally:
        await engine.dispose()


async def _assert_audit_log_is_immutable(url: str) -> None:
    """The trigger rejects UPDATE/DELETE on audit_log; the CHECK was widened to the new actions.

    The probe row uses an ORIGINAL action so it survives the downgrade's narrowed CHECK (and the
    trigger blocks deleting it). The widening is confirmed from the catalog, not a new-action row.
    """
    engine = create_async_engine(url)
    insert = text(
        "INSERT INTO audit_log "
        "(occurred_at, action, severity, result, actor, meta, prev_hash, entry_hash) "
        "VALUES (now(), 'setup_token.issued', 'info', 'success', 'system', '{}', :p, :e)"
    )
    marker = {"p": "0" * 64, "e": "a" * 64}
    try:
        async with engine.begin() as conn:
            await conn.execute(insert, marker)
        with pytest.raises(DBAPIError):  # UPDATE blocked by the immutability trigger
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE audit_log SET actor = 'x' WHERE entry_hash = :e"),
                    {"e": marker["e"]},
                )
        with pytest.raises(DBAPIError):  # DELETE blocked too
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM audit_log WHERE entry_hash = :e"), {"e": marker["e"]}
                )
        async with engine.connect() as conn:
            defn = (
                await conn.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = "
                        "'auditaction' AND conrelid = 'audit_log'::regclass"
                    )
                )
            ).scalar_one()
        assert "oidc.login.succeeded" in defn
        assert "audit.chain.verification_failed" in defn
        # 0006 widened the CHECK for the wiring + rotation events.
        assert "authentik.wiring.succeeded" in defn
        assert "bootstrap.token.rotated" in defn
    finally:
        await engine.dispose()


async def _assert_authentik_integration_schema(url: str) -> None:
    """0005 built the runtime-wired Authentik integration singleton (named columns catch drift)."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "SELECT id, base_url, internal_base_url, client_id, client_secret_enc, "
                    "provider_pk, sa_token_enc, app_slug, wired_at, created_at, updated_at "
                    "FROM authentik_integration"
                )
            )
            result = await conn.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname = "
                    "'ck_authentik_integration_singleton'"
                )
            )
            assert {row[0] for row in result} == {"ck_authentik_integration_singleton"}
    finally:
        await engine.dispose()


def test_upgrade_downgrade_roundtrip() -> None:
    settings = Settings()
    cfg = build_config(settings)

    command.upgrade(cfg, "head")
    # Prove the upgrade actually built the schema (not a silent no-op).
    asyncio.run(_assert_setup_state_queryable(settings.database_url))
    asyncio.run(_assert_audit_schema(settings.database_url))
    asyncio.run(_assert_auth_schema(settings.database_url))
    asyncio.run(_assert_audit_log_is_immutable(settings.database_url))
    asyncio.run(_assert_authentik_integration_schema(settings.database_url))

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
