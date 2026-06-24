"""The serve entrypoint's socket planning: one listener normally, two when break-glass is on."""

import socket

import pytest

from hex.config import Settings
from hex.serve import _bind, _family_for, _listener_addrs


def test_one_listener_when_breakglass_disabled() -> None:
    addrs = _listener_addrs(Settings(breakglass_enabled=False))
    assert addrs == [("0.0.0.0", 8000)]


def test_second_listener_when_breakglass_enabled() -> None:
    addrs = _listener_addrs(
        Settings(
            breakglass_enabled=True, breakglass_listen_host="127.0.0.1", breakglass_listen_port=8001
        )
    )
    assert addrs == [("0.0.0.0", 8000), ("127.0.0.1", 8001)]


def test_rejects_colliding_ports() -> None:
    with pytest.raises(ValueError, match="differ"):
        _listener_addrs(
            Settings(breakglass_enabled=True, serve_port=8000, breakglass_listen_port=8000)
        )


def test_family_for_picks_ipv4_or_ipv6() -> None:
    assert _family_for("127.0.0.1") is socket.AF_INET
    assert _family_for("0.0.0.0") is socket.AF_INET
    assert _family_for("::1") is socket.AF_INET6
    assert _family_for("fc00::1") is socket.AF_INET6


def test_bind_returns_a_bound_socket() -> None:
    sock = _bind("127.0.0.1", 0)  # port 0 → OS picks an ephemeral port
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        sock.close()
