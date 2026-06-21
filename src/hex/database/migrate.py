"""Programmatic Alembic config + upgrade used at startup (docs/BOOTSTRAP.md)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

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
