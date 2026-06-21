"""Alembic migration round-trip against real Postgres (CI pg job only).

Environment-gated, not skipped-to-be-green: the CI Postgres job sets HEX_RUN_PG_TESTS=1
(plus HEX_DB_*) so these run there. SQLite tests build schema from metadata instead.
"""

import asyncio
import os

import pytest
from alembic import command
from sqlalchemy import text
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


def test_upgrade_downgrade_roundtrip() -> None:
    settings = Settings()
    cfg = build_config(settings)

    command.upgrade(cfg, "head")
    # Prove the upgrade actually built the schema (not a silent no-op).
    asyncio.run(_assert_setup_state_queryable(settings.database_url))
    asyncio.run(_assert_audit_schema(settings.database_url))

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
