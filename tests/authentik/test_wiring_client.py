"""AuthentikWiringClient: provider-secret read-back and idempotent SA-token minting."""

import httpx
import pytest
import respx

from hex.authentik import AuthentikUnreachable, AuthentikWiringClient, WiringFailed
from hex.authentik.names import SA_TOKEN_IDENTIFIER

_BASE = "http://ak.test"
_TOKEN = "bootstrap-token"  # noqa: S105 — fake token for tests
_API = f"{_BASE}/api/v3"
_VIEW_KEY = f"{_API}/core/tokens/{SA_TOKEN_IDENTIFIER}/view_key/"


def _client(http: httpx.AsyncClient) -> AuthentikWiringClient:
    return AuthentikWiringClient(_BASE, _TOKEN, http)


@respx.mock
async def test_get_provider_secret_returns_the_secret() -> None:
    respx.get(f"{_API}/providers/oauth2/7/").mock(
        return_value=httpx.Response(200, json={"client_id": "x", "client_secret": "sek"})
    )
    async with httpx.AsyncClient() as http:
        assert await _client(http).get_provider_secret(7) == "sek"


@respx.mock
async def test_get_provider_secret_missing_raises_wiring_failed() -> None:
    respx.get(f"{_API}/providers/oauth2/7/").mock(
        return_value=httpx.Response(200, json={"client_id": "x", "client_secret": ""})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await _client(http).get_provider_secret(7)


@respx.mock
async def test_get_provider_secret_http_error_is_unreachable() -> None:
    respx.get(f"{_API}/providers/oauth2/7/").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).get_provider_secret(7)


@respx.mock
async def test_ensure_token_creates_then_returns_key() -> None:
    create = respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(201, json={}))
    respx.get(_VIEW_KEY).mock(return_value=httpx.Response(200, json={"key": "sa-key"}))
    async with httpx.AsyncClient() as http:
        key = await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)
    assert key == "sa-key"
    assert create.called


@respx.mock
async def test_ensure_token_tolerates_duplicate_identifier_400() -> None:
    # Re-running bootstrap: the identifier already exists (400); view_key is still authoritative.
    respx.post(f"{_API}/core/tokens/").mock(
        return_value=httpx.Response(400, json={"identifier": ["already exists"]})
    )
    respx.get(_VIEW_KEY).mock(return_value=httpx.Response(200, json={"key": "sa-key"}))
    async with httpx.AsyncClient() as http:
        assert await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER) == "sa-key"


@respx.mock
async def test_ensure_token_missing_key_raises_wiring_failed() -> None:
    respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(201, json={}))
    respx.get(_VIEW_KEY).mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)


@respx.mock
async def test_ensure_token_create_server_error_is_unreachable() -> None:
    respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)


@respx.mock
async def test_ensure_token_non_duplicate_4xx_is_unreachable() -> None:
    # A 403 (permission) on create is NOT a tolerated duplicate — it must surface, not be swallowed.
    respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(403))
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)


@respx.mock
async def test_ensure_token_view_key_server_error_is_unreachable() -> None:
    # Token created, but reading its key fails transiently → retryable AuthentikUnreachable.
    respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(201, json={}))
    respx.get(_VIEW_KEY).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)


@respx.mock
async def test_ensure_token_validation_400_without_token_is_wiring_failed() -> None:
    # A 400 that wasn't a duplicate leaves no token → view_key 404 → permanent WiringFailed,
    # not a transient/retryable AuthentikUnreachable.
    respx.post(f"{_API}/core/tokens/").mock(
        return_value=httpx.Response(400, json={"intent": ["invalid"]})
    )
    respx.get(_VIEW_KEY).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await _client(http).ensure_service_account_token(11, SA_TOKEN_IDENTIFIER)
