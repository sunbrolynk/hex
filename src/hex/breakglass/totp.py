"""Offline TOTP second factor for break-glass.

Validated entirely by HEx against the locally-stored seed — never via Authentik, email, SMS,
or push. The recovery path must not depend on the thing that might be broken (ADR 0008). pyotp's
``verify`` compares in constant time.
"""

from datetime import UTC, datetime

import pyotp

_VALID_WINDOW = 1  # accept the adjacent ±30s step to tolerate clock drift


def verify_totp(secret: str, code: str, *, for_time: datetime | int | None = None) -> bool:
    """True if ``code`` is valid for ``secret`` now (or at ``for_time``, for tests)."""
    if not secret or not code:
        return False
    # An int epoch is normalised to an aware UTC datetime — pyotp.verify's signature wants a
    # datetime, while tests pin a fixed integer time for determinism.
    when = datetime.fromtimestamp(for_time, tz=UTC) if isinstance(for_time, int) else for_time
    try:
        return pyotp.TOTP(secret).verify(code, for_time=when, valid_window=_VALID_WINDOW)
    except ValueError:
        return False  # fail secure on a degenerate seed/time rather than propagating
