"""Cooldown lockout: trips after N failures in the window, auto-clears after the cooldown."""

from hex.breakglass.lockout import CooldownLimiter


def _limiter() -> CooldownLimiter:
    return CooldownLimiter(max_attempts=3, window_seconds=300.0, cooldown_seconds=900.0)


def test_not_locked_initially() -> None:
    assert _limiter().locked(now=0.0) is False


def test_locks_after_max_failures_in_window() -> None:
    lim = _limiter()
    for t in (0.0, 1.0, 2.0):
        lim.record_failure(t)
    assert lim.locked(now=3.0) is True


def test_stays_locked_through_cooldown_then_clears() -> None:
    lim = _limiter()
    for t in (0.0, 1.0, 2.0):
        lim.record_failure(t)
    assert lim.locked(now=2.0 + 899.0) is True  # still within the 900s cooldown
    assert lim.locked(now=2.0 + 901.0) is False  # cooldown elapsed → cleared
    assert lim.locked(now=2.0 + 902.0) is False  # and stays clear (failures reset)


def test_failures_outside_window_do_not_accumulate() -> None:
    lim = _limiter()
    # Each failure is more than the 300s window after the previous → never three "recent" together.
    for t in (0.0, 400.0, 800.0):
        lim.record_failure(t)
    assert lim.locked(now=800.0) is False


def test_reset_clears_failures_and_lock() -> None:
    lim = _limiter()
    for t in (0.0, 1.0, 2.0):
        lim.record_failure(t)
    lim.reset()
    assert lim.locked(now=3.0) is False
