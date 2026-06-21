"""Programmatic Alembic config + upgrade used at startup (docs/BOOTSTRAP.md)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from hex.config import Settings

# Migrations ship inside the package so the image's ``COPY src/`` carries them and the path
# resolves whether run from source or the installed wheel.
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def build_config(settings: Settings) -> Config:
    """Alembic config wired to HEx's migrations dir and DSN (no on-disk alembic.ini)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def upgrade_to_head(settings: Settings) -> None:
    """Apply all pending migrations. Synchronous — call from a worker thread, not the loop."""
    command.upgrade(build_config(settings), "head")


async def assert_at_head(settings: Settings) -> None:
    """Refuse to boot if the DB schema is behind head (production, auto-migrate disabled).

    Guards the operator-runs-migrations path: with auto-migrate off, a stale or unmigrated DB
    must fail closed rather than serve against the wrong schema.

    Raises:
        RuntimeError: If the DB's current revision is not the latest migration.
    """
    head = ScriptDirectory.from_config(build_config(settings)).get_current_head()
    engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as conn:
            current = await conn.run_sync(
                lambda sync: MigrationContext.configure(sync).get_current_revision()
            )
    finally:
        await engine.dispose()
    if current != head:
        raise RuntimeError(
            "Database schema is not at head and HEX_DB_AUTO_MIGRATE is disabled. "
            f"Run 'alembic upgrade head' before starting (current={current!r}, head={head!r})."
        )
