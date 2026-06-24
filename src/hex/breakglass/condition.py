"""Break-glass condition gate: the IdP-health half of "is break-glass allowed right now?".

If a healthy Authentik is reachable, the emergency path stays closed (ADR 0008) — break-glass
exists for when it is *not*. The network/local-only half is enforced at the route's listener
(Slice 4-2), not here.
"""

from hex.breakglass.config import BreakGlassConfig


def condition_met(config: BreakGlassConfig, *, idp_healthy: bool) -> bool:
    """True when the IdP-health gate permits break-glass.

    ``require_idp_down=False`` disables the gate (always permitted). When True, break-glass is
    permitted only while the IdP is unhealthy; a healthy, reachable IdP closes the path.
    """
    if not config.require_idp_down:
        return True
    return not idp_healthy
