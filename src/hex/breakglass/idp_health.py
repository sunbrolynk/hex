"""Fast, fail-secure IdP health probe for the break-glass condition gate (ADR 0008).

Break-glass opens precisely when Authentik is unreachable, so the probe must be quick and treat ANY
doubt — error, timeout, non-2xx, or no configured base URL — as "down". The recovery path cannot
hang on, or depend on, the thing that might be broken.
"""

import httpx

_READY_PATH = "/-/health/ready/"
_TIMEOUT = 2.0  # short: when Authentik is down the probe must fail fast, not hang the recovery path


async def idp_healthy(base_url: str, http: httpx.AsyncClient) -> bool:
    """True only if Authentik's readiness endpoint answers 2xx within the timeout; else False."""
    if not base_url:
        return False
    try:
        resp = await http.get(f"{base_url.rstrip('/')}{_READY_PATH}", timeout=_TIMEOUT)
    except httpx.HTTPError:
        return False
    return resp.status_code < 300
