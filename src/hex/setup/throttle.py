"""Per-process fixed-window failure limiter for the setup-unlock surface.

Deliberately minimal: a single-owner, single-origin first-run action behind a ≥256-bit token
does not need distributed rate-limiting. This is defense-in-depth and will be superseded by the
shared limiter that invites/break-glass introduce. Only *failed* attempts count, so a correct
token never costs the operator budget. Time is injected so it is testable without patching the
clock.

Keying is per client host: behind a reverse proxy that collapses to the proxy address, so the
setup surface must be LAN/loopback-bound during first run (docs/BOOTSTRAP.md). The ``_windows``
map is unbounded by key — acceptable while the surface is LAN-bound and short-lived; the shared
limiter that replaces this will own eviction.
"""


class AttemptLimiter:
    """Block a key once it records ``max_attempts`` failures within ``window_seconds``."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._windows: dict[str, tuple[float, int]] = {}

    def _window_for(self, key: str, now: float) -> tuple[float, int]:
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self._window:
            return now, 0  # window elapsed → fresh
        return start, count

    def blocked(self, key: str, now: float) -> bool:
        """True if ``key`` has already hit the failure limit in the current window."""
        return self._window_for(key, now)[1] >= self._max

    def record_failure(self, key: str, now: float) -> None:
        """Count one failed attempt against ``key``."""
        start, count = self._window_for(key, now)
        self._windows[key] = (start, count + 1)
