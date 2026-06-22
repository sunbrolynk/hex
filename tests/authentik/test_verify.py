"""The `hex.authentik.verify` diagnostic entrypoint: exit codes for the three outcomes."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from hex.authentik import verify
from hex.config import Settings

_BASE = "http://ak.test"
_API = f"{_BASE}/api/v3"


def _settings(token: str) -> Settings:
    return Settings(authentik_bootstrap_token=SecretStr(token), authentik_oidc_app_slug="hex")


def _mock_all_present() -> None:
    respx.get(f"{_BASE}/-/health/ready/").mock(return_value=httpx.Response(204))
    respx.get(f"{_API}/core/applications/").mock(
        return_value=httpx.Response(200, json={"results": [{"slug": "hex", "name": "HEx"}]})
    )
    respx.get(f"{_API}/providers/oauth2/").mock(
        return_value=httpx.Response(
            200, json={"results": [{"pk": 7, "name": "HEx web BFF", "client_id": "abc"}]}
        )
    )
    respx.get(f"{_API}/core/groups/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": 3, "name": "HEx Provisioners"}]})
    )
    respx.get(f"{_API}/core/users/").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"pk": 11, "username": "hex-provisioner", "is_superuser": False}]},
        )
    )


async def test_returns_2_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "get_settings", lambda: _settings(""))
    assert await verify._run(_BASE) == 2


@respx.mock
async def test_returns_0_when_wiring_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "get_settings", lambda: _settings("tok"))
    _mock_all_present()
    assert await verify._run(_BASE) == 0


@respx.mock
async def test_returns_1_when_object_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "get_settings", lambda: _settings("tok"))
    respx.get(f"{_BASE}/-/health/ready/").mock(return_value=httpx.Response(204))
    respx.get(f"{_API}/core/applications/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    assert await verify._run(_BASE) == 1
