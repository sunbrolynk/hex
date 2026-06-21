"""AttemptLimiter: failure-only fixed-window blocking."""

from hex.setup import AttemptLimiter


def test_blocks_only_after_max_failures() -> None:
    limiter = AttemptLimiter(max_attempts=2, window_seconds=60.0)
    assert limiter.blocked("ip", now=0.0) is False
    limiter.record_failure("ip", now=0.0)
    assert limiter.blocked("ip", now=0.0) is False  # 1 failure < 2
    limiter.record_failure("ip", now=0.0)
    assert limiter.blocked("ip", now=0.0) is True  # 2 failures == limit


def test_window_resets_after_it_elapses() -> None:
    limiter = AttemptLimiter(max_attempts=2, window_seconds=10.0)
    limiter.record_failure("ip", now=0.0)
    limiter.record_failure("ip", now=1.0)
    assert limiter.blocked("ip", now=5.0) is True  # same window
    assert limiter.blocked("ip", now=10.0) is False  # window elapsed → reset
    # A fresh failure after reset starts a new count, not carrying the old one.
    limiter.record_failure("ip", now=10.0)
    assert limiter.blocked("ip", now=10.0) is False


def test_keys_are_independent() -> None:
    limiter = AttemptLimiter(max_attempts=1, window_seconds=60.0)
    limiter.record_failure("a", now=0.0)
    assert limiter.blocked("a", now=0.0) is True
    assert limiter.blocked("b", now=0.0) is False
