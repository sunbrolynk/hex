"""Cumulative-failure lockout for the setup-unlock surface (in-process tripwire).

Unlike the windowed throttle, this never self-resets: once total failures cross the threshold the
install is *frozen* and the token is burned (docs/BOOTSTRAP.md). Recovery is a HEx restart, which
builds a fresh counter (clearing the freeze) and re-mints the token. Only failed attempts count.

The count is **global**, not per-client: a single-owner, single-origin first run has nothing to
partition, and a global tally can't be evaded by rotating source addresses. The per-window,
per-client soft limit is the separate ``AttemptLimiter``.
"""


class LockoutCounter:
    """Counts setup-unlock failures globally and latches a freeze at the threshold."""

    def __init__(self) -> None:
        self._failures = 0
        self._frozen = False

    @property
    def frozen(self) -> bool:
        """True once a lockout has tripped; stays true until the process restarts."""
        return self._frozen

    def record(self, threshold: int) -> int:
        """Count a failure; latch the freeze at ``threshold``; return the new total."""
        self._failures += 1
        if self._failures >= threshold:
            self._frozen = True
        return self._failures
