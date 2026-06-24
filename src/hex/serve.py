"""Container entrypoint: serve HEx on the proxy-facing socket plus, when break-glass is enabled,
a separate LAN-bound socket for the emergency path (ADR 0008, breakglass-local-only-enforcement).

One uvicorn process, two sockets — the route guard keys off which socket a request arrived on, so
the break-glass path is unreachable through the proxy-facing listener. ``create_app`` is unchanged,
so dev can still run ``uvicorn hex.api.main:create_app --factory`` on a single port.
"""

import socket

import uvicorn

from hex.api.main import create_app
from hex.config import Settings, get_settings


def _listener_addrs(settings: Settings) -> list[tuple[str, int]]:
    """The (host, port) sockets to open: the main one, plus break-glass when enabled."""
    addrs = [(settings.serve_host, settings.serve_port)]
    if settings.breakglass_enabled:
        if settings.breakglass_listen_port == settings.serve_port:
            raise ValueError(
                "HEX_BREAKGLASS_LISTEN_PORT must differ from HEX_SERVE_PORT — the break-glass "
                "listener needs its own socket to be told apart from the proxy-facing one."
            )
        addrs.append((settings.breakglass_listen_host, settings.breakglass_listen_port))
    return addrs


def _family_for(host: str) -> socket.AddressFamily:
    """IPv6 for a host containing ':' (e.g. ``::1``), else IPv4."""
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def _bind(host: str, port: int) -> socket.socket:
    """A bound, address-reusable TCP socket for uvicorn to listen on."""
    sock = socket.socket(_family_for(host), socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def main() -> None:  # pragma: no cover - blocking server run, exercised in the live demo
    settings = get_settings()
    app = create_app(settings)
    sockets = [_bind(host, port) for host, port in _listener_addrs(settings)]
    # proxy_headers=False: the break-glass guard reads the real TCP peer, never a forwarded
    # header (non-negotiable #2). The reverse proxy fronts only the main socket; HEx does not
    # trust X-Forwarded-* on either listener.
    uvicorn.Server(uvicorn.Config(app, proxy_headers=False)).run(sockets=sockets)


if __name__ == "__main__":  # pragma: no cover
    main()
