"""assert_at_head: refuse to boot on a stale schema when auto-migrate is off."""

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hex.config import Settings
from hex.database.migrate import assert_at_head, build_config
from tests.conftest import make_settings


async def _make_sqlite(url: str, stamp: str | None) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            if stamp is None:
                await conn.execute(text("SELECT 1"))  # materialize an empty DB file
            else:
                await conn.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": stamp}
                )
    finally:
        await engine.dispose()


def _point_at(monkeypatch: pytest.MonkeyPatch, url: str) -> Settings:
    monkeypatch.setattr(Settings, "database_url", property(lambda _self: url))
    return make_settings(env="production", db_auto_migrate=False)


async def test_assert_at_head_raises_when_unmigrated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}"  # type: ignore[operator]
    settings = _point_at(monkeypatch, url)
    await _make_sqlite(url, stamp=None)

    with pytest.raises(RuntimeError, match="not at head"):
        await assert_at_head(settings)


async def test_assert_at_head_passes_when_at_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}"  # type: ignore[operator]
    settings = _point_at(monkeypatch, url)
    head = ScriptDirectory.from_config(build_config(settings)).get_current_head()
    assert head is not None
    await _make_sqlite(url, stamp=head)

    await assert_at_head(settings)  # no raise
