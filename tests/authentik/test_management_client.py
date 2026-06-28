"""AuthentikManagementClient: SA-token invitation minting + fail-closed error paths."""

import httpx
import pytest
import respx

from hex.authentik.errors import AuthentikUnreachable, WiringFailed
from hex.authentik.management_client import AuthentikManagementClient

_BASE = "http://ak.test"


def _client(http: httpx.AsyncClient) -> AuthentikManagementClient:
    return AuthentikManagementClient(_BASE, "sa-token", http)


@respx.mock
async def test_create_invitation_resolves_flow_and_posts() -> None:
    flow = respx.get(f"{_BASE}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": "flow-pk"}]})
    )
    post = respx.post(f"{_BASE}/api/v3/stages/invitation/invitations/").mock(
        return_value=httpx.Response(201, json={"pk": "itok-1"})
    )
    async with httpx.AsyncClient() as http:
        token = await _client(http).create_invitation(
            name="n", flow_slug="hex-enrollment", fixed_data={"x": 1}, ttl_seconds=60
        )
    assert token == "itok-1"
    assert flow.called and post.called
    body = post.calls.last.request.read().decode()
    assert '"single_use":true' in body
    assert '"flow":"flow-pk"' in body


@respx.mock
async def test_unknown_flow_raises_wiring_failed() -> None:
    respx.get(f"{_BASE}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await _client(http).create_invitation(
                name="n", flow_slug="missing", fixed_data={}, ttl_seconds=60
            )


@respx.mock
async def test_flow_lookup_transport_error_is_unreachable() -> None:
    respx.get(f"{_BASE}/api/v3/flows/instances/").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).create_invitation(
                name="n", flow_slug="hex-enrollment", fixed_data={}, ttl_seconds=60
            )


@respx.mock
async def test_invitation_create_error_is_unreachable() -> None:
    respx.get(f"{_BASE}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": "flow-pk"}]})
    )
    respx.post(f"{_BASE}/api/v3/stages/invitation/invitations/").mock(
        return_value=httpx.Response(500)
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthentikUnreachable):
            await _client(http).create_invitation(
                name="n", flow_slug="hex-enrollment", fixed_data={}, ttl_seconds=60
            )


@respx.mock
async def test_invitation_without_pk_raises_wiring_failed() -> None:
    respx.get(f"{_BASE}/api/v3/flows/instances/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": "flow-pk"}]})
    )
    respx.post(f"{_BASE}/api/v3/stages/invitation/invitations/").mock(
        return_value=httpx.Response(201, json={})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await _client(http).create_invitation(
                name="n", flow_slug="hex-enrollment", fixed_data={}, ttl_seconds=60
            )
