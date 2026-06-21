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
            await conn.execute(text("SELECT id, phase FROM setup_state"))
    finally:
        await engine.dispose()


def test_upgrade_downgrade_roundtrip() -> None:
    settings = Settings()
    cfg = build_config(settings)

    command.upgrade(cfg, "head")
    # Prove the upgrade actually built the schema (not a silent no-op).
    asyncio.run(_assert_setup_state_queryable(settings.database_url))

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
