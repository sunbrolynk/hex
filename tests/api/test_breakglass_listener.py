"""The break-glass listener guard: reachable only on the LAN socket from a local client."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from hex.api.guards import _is_local_client, require_breakglass_listener
from hex.api.main import create_app
from hex.config import Settings

_BG_PORT = 8001


def _settings(
    *, enabled: bool = True, listen_port: int = _BG_PORT, local_only: bool = True
) -> Settings:
    return Settings(
        breakglass_enabled=enabled,
        breakglass_listen_port=listen_port,
        breakglass_local_only=local_only,
    )


def _request(
    settings: Settings,
    *,
    server: tuple[str, int] | None,
    client: tuple[str, int] | None,
) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "server": server,
            "client": client,
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        }
    )


async def test_allows_local_client_on_breakglass_listener() -> None:
    req = _request(_settings(), server=("127.0.0.1", _BG_PORT), client=("127.0.0.1", 5000))
    await require_breakglass_listener(req)  # no raise


@pytest.mark.parametrize(
    ("server", "client"),
    [
        (("0.0.0.0", 8000), ("127.0.0.1", 5000)),  # arrived on the proxy-facing socket
        (("192.168.1.10", _BG_PORT), ("8.8.8.8", 5000)),  # right socket, non-local client
        (None, ("127.0.0.1", 5000)),  # no server addr at all
        (("192.168.1.10", _BG_PORT), None),  # no client addr
    ],
)
async def test_404s_off_listener_or_for_remote_client(
    server: tuple[str, int] | None, client: tuple[str, int] | None
) -> None:
    req = _request(_settings(), server=server, client=client)
    with pytest.raises(HTTPException) as exc:
        await require_breakglass_listener(req)
    assert exc.value.status_code == 404


async def test_local_only_off_relaxes_client_check_but_keeps_listener() -> None:
    # local_only=False allows a non-local peer ON the break-glass listener...
    settings = _settings(local_only=False)
    req = _request(settings, server=("0.0.0.0", _BG_PORT), client=("8.8.8.8", 5000))
    await require_breakglass_listener(req)  # no raise
    # ...but the listener requirement still stands: the proxy socket is always 404.
    off = _request(settings, server=("0.0.0.0", 8000), client=("8.8.8.8", 5000))
    with pytest.raises(HTTPException) as exc:
        await require_breakglass_listener(off)
    assert exc.value.status_code == 404


async def test_404s_when_breakglass_disabled_even_on_listener() -> None:
    req = _request(
        _settings(enabled=False), server=("127.0.0.1", _BG_PORT), client=("127.0.0.1", 1)
    )
    with pytest.raises(HTTPException) as exc:
        await require_breakglass_listener(req)
    assert exc.value.status_code == 404


async def test_route_is_mounted_and_guarded_404s_by_default(client: AsyncClient) -> None:
    # End-to-end: the route exists but the guard closes it on the default (proxy) transport.
    resp = await client.get("/auth/breakglass")
    assert resp.status_code == 404


async def test_probe_returns_ready_when_guard_passes() -> None:
    # With the listener guard satisfied, the placeholder probe answers (proves it's wired in).
    app = create_app(Settings(db_auto_migrate=False))
    app.dependency_overrides[require_breakglass_listener] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/auth/breakglass")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("10.1.2.3", True),
        ("192.168.0.5", True),
        ("172.16.4.4", True),
        ("::1", True),
        ("fc00::1", True),
        ("8.8.8.8", False),
        ("1.1.1.1", False),
        ("not-an-ip", False),
        (None, False),
    ],
)
def test_is_local_client(host: str | None, expected: bool) -> None:
    assert _is_local_client(host) is expected
