"""The dashboard read: the tiles a user actually has, derived from the ledger.

Strictly per-user (non-negotiable #8): the only ledger read is ``user_active_entries(user.id)``,
SQL-scoped to the requester, so one user can never see another's tiles. Read-only here — layout,
drag/drop, and theming land in 6-4b/6-4c (ADR 0014). A ledger entry whose provider is not currently
registered is omitted (and logged): every tile resolves to a real provider. Active-but-not-yet-live
grants (pending/partial) are shown with their status but are not clickable — only GRANTED tiles
link.
"""

import logging
from typing import Annotated, Protocol, runtime_checkable

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import require_user
from hex.api.schemas import DashboardResponse, TileResponse
from hex.database import LedgerManager, User, get_session
from hex.providers import IntegrationMode, Provider, ProvisionState

log = logging.getLogger("hex.dashboard")
router = APIRouter(tags=["dashboard"])

# A tile deep-link is a navigation target rendered into an <a href>. Only http(s) is allowed — a
# javascript:/data: value would be a stored-XSS sink once the link becomes owner-configured.
_SAFE_SCHEMES = ("https://", "http://")


@runtime_checkable
class _Linkable(Protocol):
    """A provider that exposes a deep-link. The deep-link is not yet part of the frozen provider
    contract (owner-configured per LIFECYCLE §4); read it structurally until that lands."""

    link: str


def _tile_url(provider: Provider) -> str | None:
    """The provider's deep-link, or None when absent or not a safe http(s) navigation target."""
    if not isinstance(provider, _Linkable):
        return None
    return provider.link if provider.link.startswith(_SAFE_SCHEMES) else None


@router.get("/dashboard")
async def get_dashboard(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardResponse:
    """The signed-in user's tiles — one per active grant the registry can still resolve."""
    registry = request.app.state.registry
    tiles: list[TileResponse] = []
    for entry in await LedgerManager(session).user_active_entries(user.id):
        provider = registry.get(entry.provider_id)
        if provider is None:
            # A grant whose provider is gone (disabled/removed). Don't surface an unresolvable tile;
            # reconciliation/offboard (6-6/6-7) own the ledger-vs-reality gap.
            log.warning("dashboard: no registered provider for grant %r", entry.provider_id)
            continue
        # Only a GRANTED tile is clickable: a pending/partial grant is shown (with its status) but
        # not yet live, so we don't deep-link the user into access they don't have.
        live = entry.state == ProvisionState.GRANTED
        tiles.append(
            TileResponse(
                provider_id=provider.id,
                name=provider.name,
                category=provider.category,
                state=entry.state.value,
                integration_mode=provider.integration_mode.value,
                url=_tile_url(provider) if live else None,
                seamless=provider.integration_mode == IntegrationMode.SSO_GROUP,
            )
        )
    return DashboardResponse(tiles=tiles)
