"""Data access for the runtime-wired Authentik integration (singleton).

Persistence only: it stores already-encrypted secret blobs and never touches the broker.
Encryption happens at the business boundary — the bootstrap orchestrator encrypts before
writing, the config resolver decrypts after reading (non-negotiable #4).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database.models import AuthentikIntegration

_SINGLETON_ID = 1


class AuthentikIntegrationManager:
    """Read/write the single Authentik-integration row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> AuthentikIntegration | None:
        """The integration row, or None before bootstrap has wired anything."""
        return (
            await self._session.execute(
                select(AuthentikIntegration).where(AuthentikIntegration.id == _SINGLETON_ID)
            )
        ).scalar_one_or_none()

    async def get_or_create(self) -> AuthentikIntegration:
        """Return the singleton, creating an empty row on first access."""
        row = await self.get()
        if row is None:
            row = AuthentikIntegration(id=_SINGLETON_ID)
            self._session.add(row)
            await self._session.flush()
        return row

    async def set_oidc(
        self,
        *,
        base_url: str,
        internal_base_url: str,
        client_id: str,
        client_secret_enc: str,
        provider_pk: int,
        app_slug: str,
        sa_token_enc: str,
    ) -> AuthentikIntegration:
        """Persist the wired config; marks ``wired_at``. Secrets must already be encrypted.

        No commit — the caller owns the txn so the wiring + its audit row commit atomically.
        """
        row = await self.get_or_create()
        row.base_url = base_url
        row.internal_base_url = internal_base_url
        row.client_id = client_id
        row.client_secret_enc = client_secret_enc
        row.provider_pk = provider_pk
        row.app_slug = app_slug
        row.sa_token_enc = sa_token_enc
        row.wired_at = datetime.now(UTC)
        await self._session.flush()
        return row
