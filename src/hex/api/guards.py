"""Route guards for the bootstrap surface.

Bootstrap mode exposes only the setup flow; the full app stays closed until setup completes
(docs/BOOTSTRAP.md). Feature routers depend on ``forbid_until_setup_complete`` so every
protected route fails closed during first run rather than relying on the frontend to hide it.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SetupStateManager, get_session
from hex.database.models import SetupPhase

BOOTSTRAP_COOKIE = "hex_bootstrap"


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
