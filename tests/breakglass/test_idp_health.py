"""IdP health probe: fail-secure — only a 2xx counts as healthy; any doubt is 'down'."""

import httpx
import respx

from hex.breakglass.idp_health import idp_healthy

_BASE = "http://authentik:9000"
_URL = f"{_BASE}/-/health/ready/"


@respx.mock
async def test_healthy_on_2xx() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(204))
    async with httpx.AsyncClient() as http:
        assert await idp_healthy(_BASE, http) is True


@respx.mock
async def test_unhealthy_on_5xx() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        assert await idp_healthy(_BASE, http) is False


@respx.mock
async def test_unhealthy_on_transport_error() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as http:
        assert await idp_healthy(_BASE, http) is False


async def test_unhealthy_when_no_base_url() -> None:
    async with httpx.AsyncClient() as http:
        assert await idp_healthy("", http) is False
