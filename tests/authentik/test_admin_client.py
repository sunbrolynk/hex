"""AuthentikAdminClient: read/verify the blueprint objects, and the fail-secure matrix.

Security-critical (non-negotiable #3): an overprivileged or missing service account must never
read as verified, and an unhealthy/unauthorized Authentik must fail closed rather than silently
pass. Those abuse paths carry as much weight here as the happy path.
"""

from typing import Any

import httpx
import pytest
import respx

from hex.authentik import (
    AuthentikAdminClient,
    AuthentikUnreachable,
    BlueprintObjectMissing,
    OverprivilegedServiceAccount,
    VerifyReport,
)

_BASE = "http://ak.test"
_TOKEN = "bootstrap-token"  # noqa: S105 — fake token for tests, not a real credential
_API = f"{_BASE}/api/v3"
_READY = f"{_BASE}/-/health/ready/"


def _app() -> dict[str, Any]:
    return {"results": [{"slug": "hex", "name": "HEx"}]}


def _provider() -> dict[str, Any]:
    return {"results": [{"pk": 7, "name": "HEx web BFF", "client_id": "abc123"}]}


def _group() -> dict[str, Any]:
    return {"results": [{"pk": 3, "name": "HEx Provisioners", "is_superuser": False}]}


def _sa(*, is_superuser: bool = False) -> dict[str, Any]:
    return {
        "results": [
            {
                "pk": 11,
                "username": "hex-provisioner",
                "type": "service_account",
                "is_superuser": is_superuser,
            }
        ]
    }


def _mock_objects(*, sa_superuser: bool = False) -> None:
    """Register the four object endpoints. Call inside @respx.mock."""
    respx.get(f"{_API}/core/applications/").mock(return_value=httpx.Response(200, json=_app()))
    respx.get(f"{_API}/providers/oauth2/").mock(return_value=httpx.Response(200, json=_provider()))
    respx.get(f"{_API}/core/groups/").mock(return_value=httpx.Response(200, json=_group()))
    respx.get(f"{_API}/core/users/").mock(
        return_value=httpx.Response(200, json=_sa(is_superuser=sa_superuser))
    )


async def _verify(*, sa_superuser: bool = False) -> VerifyReport:
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        return await client.verify(
            app_slug="hex",
            provider_name="HEx web BFF",
            sa_username="hex-provisioner",
            group_name="HEx Provisioners",
            wait=False,
        )


@respx.mock
async def test_verify_returns_report_for_healthy_wiring() -> None:
    _mock_objects()
    report = await _verify()
    assert report.app_slug == "hex"
    assert report.provider_name == "HEx web BFF"
    assert report.client_id == "abc123"
    assert report.provider_pk == 7
    assert report.sa_username == "hex-provisioner"
    assert report.sa_pk == 11
    assert report.group_name == "HEx Provisioners"


@respx.mock
async def test_verify_rejects_superuser_service_account() -> None:
    _mock_objects(sa_superuser=True)
    with pytest.raises(OverprivilegedServiceAccount):
        await _verify(sa_superuser=True)


def test_assert_not_superuser_raises_directly() -> None:
    with pytest.raises(OverprivilegedServiceAccount):
        AuthentikAdminClient.assert_not_superuser({"username": "x", "is_superuser": True})


def test_assert_not_superuser_allows_least_privilege() -> None:
    AuthentikAdminClient.assert_not_superuser({"username": "x", "is_superuser": False})


@respx.mock
async def test_missing_application_raises_blueprint_missing() -> None:
    respx.get(f"{_API}/core/applications/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        with pytest.raises(BlueprintObjectMissing):
            await client.get_application("hex")


@respx.mock
async def test_missing_service_account_raises_blueprint_missing() -> None:
    _mock_objects()
    respx.get(f"{_API}/core/users/").mock(return_value=httpx.Response(200, json={"results": []}))
    with pytest.raises(BlueprintObjectMissing):
        await _verify()


@respx.mock
async def test_unauthorized_token_is_unreachable_not_missing() -> None:
    respx.get(f"{_API}/core/applications/").mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        with pytest.raises(AuthentikUnreachable):
            await client.get_application("hex")


@respx.mock
async def test_transport_error_is_unreachable() -> None:
    respx.get(f"{_API}/core/groups/").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        with pytest.raises(AuthentikUnreachable):
            await client.get_group("HEx Provisioners")


@respx.mock
@pytest.mark.parametrize("status", [200, 204])
async def test_await_healthy_accepts_ready(status: int) -> None:
    respx.get(_READY).mock(return_value=httpx.Response(status))
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        await client.await_healthy(attempts=1, delay=0)


@respx.mock
async def test_await_healthy_exhausts_then_raises() -> None:
    respx.get(_READY).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        with pytest.raises(AuthentikUnreachable):
            await client.await_healthy(attempts=2, delay=0)


@respx.mock
async def test_await_healthy_survives_transient_errors_then_succeeds() -> None:
    route = respx.get(_READY)
    route.side_effect = [httpx.ConnectError("not yet"), httpx.Response(204)]
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        await client.await_healthy(attempts=3, delay=0)


@respx.mock
async def test_bearer_token_is_sent() -> None:
    route = respx.get(f"{_API}/core/applications/").mock(
        return_value=httpx.Response(200, json=_app())
    )
    async with httpx.AsyncClient() as http:
        client = AuthentikAdminClient(_BASE, _TOKEN, http)
        await client.get_application("hex")
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {_TOKEN}"
