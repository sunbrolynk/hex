"""Break-glass credential verification — pure, fail-secure, uniform on failure.

Combines the enabled flag, the IdP-down condition, the Argon2id passphrase, and the offline
TOTP into a single outcome. No DB, no network, no audit — the route owns those (Slice 4-2).
Negative paths do equivalent work (a real or decoy Argon2 verify) and the three credential
factors are always all evaluated, so neither timing nor the returned outcome reveals *which*
factor was wrong.
"""

import hmac
from datetime import datetime
from enum import Enum

from hex.breakglass import password
from hex.breakglass.condition import condition_met
from hex.breakglass.config import BreakGlassConfig
from hex.breakglass.totp import verify_totp


class BreakGlassOutcome(Enum):
    """Result of a break-glass attempt. Only ``OK`` grants; the rest are the caller's to audit."""

    DISABLED = "disabled"
    CONDITION_NOT_MET = "condition_not_met"
    BAD_CREDENTIALS = "bad_credentials"
    OK = "ok"


def verify_breakglass(
    config: BreakGlassConfig,
    *,
    username: str,
    password_attempt: str,
    totp_code: str,
    idp_healthy: bool,
    for_time: datetime | int | None = None,
) -> BreakGlassOutcome:
    """Evaluate an attempt against the resolved config and current IdP health."""
    if not config.enabled:
        password.decoy_verify(password_attempt)  # uniform timing vs. an enabled config
        return BreakGlassOutcome.DISABLED

    if not condition_met(config, idp_healthy=idp_healthy):
        password.decoy_verify(password_attempt)
        return BreakGlassOutcome.CONDITION_NOT_MET

    # Evaluate every factor regardless of an earlier mismatch — no short-circuit oracle.
    # Compare on UTF-8 bytes: hmac.compare_digest raises on non-ASCII str, and username is
    # fully attacker-controlled — a raise would both break "never raises" and leak the factor.
    user_ok = hmac.compare_digest(username.encode(), config.username.encode())
    pass_ok = password.verify_password(password_attempt, config.password_hash)
    totp_ok = verify_totp(config.totp_secret, totp_code, for_time=for_time)
    if user_ok and pass_ok and totp_ok:
        return BreakGlassOutcome.OK
    return BreakGlassOutcome.BAD_CREDENTIALS
