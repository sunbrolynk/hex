"""Break-glass owner credential: the one local login, for when Authentik is down (ADR 0008)."""

from hex.breakglass.config import BreakGlassConfig, BreakGlassConfigError
from hex.breakglass.verifier import BreakGlassOutcome, verify_breakglass

__all__ = [
    "BreakGlassConfig",
    "BreakGlassConfigError",
    "BreakGlassOutcome",
    "verify_breakglass",
]
