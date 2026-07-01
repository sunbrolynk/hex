"""The grantable-service catalog: every registered provider + the tiers it offers.

Owner-only — it defines what an invite may grant/offer, and drives the owner's selectable
invite/grant UI (never free text; ADR 0015). Tier *keys + labels* only: the server holds the actual
structured grant a key resolves to, so no grant blob crosses the wire. Empty until real providers
land (Phase 4); the demo providers populate it in dev.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from hex.api.auth_routes.dependencies import require_owner
from hex.api.guards import forbid_until_setup_complete
from hex.api.schemas import ProviderSummary, TierOption
from hex.database import User

router = APIRouter(tags=["providers"])


@router.get("/providers", dependencies=[Depends(forbid_until_setup_complete)])
async def list_providers(
    request: Request,
    owner: Annotated[User, Depends(require_owner)],
) -> list[ProviderSummary]:
    """Every registered provider with its grantable tiers. Owner-only."""
    registry = request.app.state.registry
    return [
        ProviderSummary(
            id=provider.id,
            name=provider.name,
            category=provider.category,
            integration_mode=provider.integration_mode.value,
            tiers=[
                TierOption(key=t.key, label=t.label, description=t.description)
                for t in provider.available_grants()
            ],
        )
        for provider in registry.all()
    ]
