"""Break-glass emergency surface — reachable only on the LAN-bound listener (ADR 0008).

Slice 4-2a wires the LAN-only boundary; the placeholder probe below exists to prove it
(reachable on the break-glass socket, 404 everywhere else). The real ``POST /auth/breakglass``
authentication lands in 4-2b behind the same guard.
"""

from fastapi import APIRouter, Depends

from hex.api.guards import require_breakglass_listener

router = APIRouter(tags=["break-glass"])


@router.get("/auth/breakglass", dependencies=[Depends(require_breakglass_listener)])
async def breakglass_probe() -> dict[str, str]:
    """Liveness probe for the break-glass listener; replaced by the auth endpoint in 4-2b."""
    return {"status": "ready"}
