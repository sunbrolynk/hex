"""Route guards for the bootstrap surface.

Bootstrap mode exposes only the setup flow; the full app stays closed until setup completes
(docs/BOOTSTRAP.md). Feature routers depend on ``forbid_until_setup_complete`` so every
protected route fails closed during first run rather than relying on the frontend to hide it.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from hex.database import SetupStateManager, get_session
from hex.database.models import SetupPhase


async def forbid_until_setup_complete(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Reject the request unless setup has completed. Server-side, never client-trusting."""
    if await SetupStateManager(session).current_phase() is not SetupPhase.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HEx is in first-run setup; this endpoint is unavailable until setup completes.",
        )
