"""AuthentikIntegrationManager: singleton access + opaque encrypted-blob persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import AuthentikIntegrationManager


async def test_get_returns_none_before_any_wiring(db_session: AsyncSession) -> None:
    assert await AuthentikIntegrationManager(db_session).get() is None


async def test_get_or_create_is_singleton(db_session: AsyncSession) -> None:
    manager = AuthentikIntegrationManager(db_session)
    first = await manager.get_or_create()
    second = await manager.get_or_create()
    assert first.id == 1
    assert second.id == 1


async def test_set_oidc_persists_blobs_and_marks_wired(db_session: AsyncSession) -> None:
    manager = AuthentikIntegrationManager(db_session)
    await manager.set_oidc(
        base_url="http://db",
        internal_base_url="http://db-internal",
        client_id="db-id",
        client_secret_enc="enc-secret-blob",
        provider_pk=7,
        app_slug="hex",
        sa_token_enc="enc-token-blob",
    )
    await db_session.commit()

    row = await manager.get()
    assert row is not None
    assert row.base_url == "http://db"
    assert row.internal_base_url == "http://db-internal"
    assert row.client_id == "db-id"
    # Stored verbatim — the manager never decrypts/encrypts; secrets are opaque to it.
    assert row.client_secret_enc == "enc-secret-blob"
    assert row.sa_token_enc == "enc-token-blob"
    assert row.provider_pk == 7
    assert row.wired_at is not None


async def test_set_oidc_updates_the_same_singleton_row(db_session: AsyncSession) -> None:
    manager = AuthentikIntegrationManager(db_session)
    await manager.set_oidc(
        base_url="http://one",
        internal_base_url="",
        client_id="id1",
        client_secret_enc="s1",
        provider_pk=1,
        app_slug="hex",
        sa_token_enc="t1",
    )
    await manager.set_oidc(
        base_url="http://two",
        internal_base_url="",
        client_id="id2",
        client_secret_enc="s2",
        provider_pk=2,
        app_slug="hex",
        sa_token_enc="t2",
    )
    await db_session.commit()
    row = await manager.get()
    assert row is not None
    assert row.id == 1
    assert row.base_url == "http://two"
    assert row.provider_pk == 2
