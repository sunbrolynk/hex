"""Shared test fixtures."""

import base64
import os
import secrets
from collections.abc import AsyncIterator

# Seed valid secrets before any Settings() is built, so create_app() passes boot validation.
# Refuse-to-boot abuse cases pass crafted Settings directly (see tests/secrets, tests/api).
os.environ.setdefault("HEX_SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("HEX_KEK", base64.b64encode(secrets.token_bytes(32)).decode())
os.environ.setdefault("HEX_DB_PASSWORD", secrets.token_urlsafe(32))
os.environ.setdefault("HEX_PROXY_SHARED_SECRET", secrets.token_urlsafe(48))

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from hex.api.main import create_app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound in-process to a freshly built app (no network)."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
