"""Cooldown lockout for the break-glass login.

Unlike the setup freeze (restart-to-recover), break-glass must stay usable in an emergency, so the
lockout auto-clears after a cooldown. Global, not per-client: the listener is LAN-bound and there is
one owner, and a global tally can't be evaded by rotating source addresses. Time is injected so it
is testable without patching the clock. Only failed attempts count.
"""


class CooldownLimiter:
    """Locks after ``max_attempts`` failures within ``window``; auto-clears ``cooldown`` later."""

    def __init__(self, max_attempts: int, window_seconds: float, cooldown_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._cooldown = cooldown_seconds
        self._failures: list[float] = []
        self._locked_until: float | None = None

    def locked(self, now: float) -> bool:
        """True while a lockout is in effect; clears the lockout once its cooldown has elapsed."""
        if self._locked_until is not None:
            if now < self._locked_until:
                return True
            self._locked_until = None
            self._failures = []
        return False

    def record_failure(self, now: float) -> None:
        """Count one failure (dropping any older than the window); trip the lockout at the limit."""
        self._failures = [t for t in self._failures if now - t < self._window]
        self._failures.append(now)
        if len(self._failures) >= self._max:
            self._locked_until = now + self._cooldown

    def reset(self) -> None:
        """Clear all state — called after a successful authentication."""
        self._failures = []
        self._locked_until = None
