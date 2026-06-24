"""Route guards for the bootstrap surface.

Bootstrap mode exposes only the setup flow; the full app stays closed until setup completes
(docs/BOOTSTRAP.md). Feature routers depend on ``forbid_until_setup_complete`` so every
protected route fails closed during first run rather than relying on the frontend to hide it.
"""

import ipaddress
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SetupStateManager, get_session
from hex.database.models import SetupPhase

BOOTSTRAP_COOKIE = "hex_bootstrap"


def _is_local_client(host: str | None) -> bool:
    """True if ``host`` is a loopback or private (RFC1918/ULA) address; False on None/garbage."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


async def require_breakglass_listener(request: Request) -> None:
    """Allow only on the LAN-bound break-glass socket from a local client; else 404.

    The break-glass path is reachable solely through the separate LAN listener (the network is the
    primary control); this dependency is the in-app re-check (right socket + private/loopback peer),
    failing closed. A 404 — not a 403 — keeps the path indistinguishable from non-existent on the
    proxy-facing socket. See breakglass-local-only-enforcement, ADR 0008.

    Arriving on the break-glass listener is always required. ``breakglass_local_only`` (default on)
    additionally requires a private/loopback peer; turning it off relaxes only that second check,
    never the listener requirement.
    """
    settings = request.app.state.settings
    server = request.scope.get("server")  # (host, port) of the socket the request arrived on
    on_listener = server is not None and server[1] == settings.breakglass_listen_port
    client = request.client.host if request.client else None
    local_ok = (not settings.breakglass_local_only) or _is_local_client(client)
    if not (settings.breakglass_enabled and on_listener and local_ok):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


async def forbid_until_setup_complete(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Reject the request unless setup has completed. Server-side, never client-trusting."""
    if await SetupStateManager(session).current_phase() is not SetupPhase.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HEx is in first-run setup; this endpoint is unavailable until setup completes.",
        )


async def require_bootstrap_phase(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Allow only in BOOTSTRAP (after the token unlock, before setup completes). Fail closed."""
    if await SetupStateManager(session).current_phase() is not SetupPhase.BOOTSTRAP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Authentik wiring is only available during bootstrap.",
        )


async def require_bootstrap_session(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Require the bootstrap-session cookie minted at unlock — proof the caller unlocked.

    Binds the bootstrap-only endpoints (wire, owner claim) to whoever passed the setup token, not
    merely anyone reaching the surface during the open window. Server-side; never client-trusting.
    """
    token = request.cookies.get(BOOTSTRAP_COOKIE)
    if not await SetupStateManager(session).verify_bootstrap_session(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="bootstrap session required"
        )
