"""LockoutCounter: global cumulative-failure freeze for the setup-unlock surface."""

from hex.setup import LockoutCounter


def test_not_frozen_until_threshold() -> None:
    lockout = LockoutCounter()
    assert lockout.frozen is False
    assert lockout.record(3) == 1
    assert lockout.record(3) == 2
    assert lockout.frozen is False
    assert lockout.record(3) == 3
    assert lockout.frozen is True


def test_count_is_global_and_cannot_be_evaded() -> None:
    """Failures accumulate toward one global freeze — rotating source addresses can't reset it."""
    lockout = LockoutCounter()
    assert lockout.record(3) == 1
    assert lockout.record(3) == 2
    assert lockout.record(3) == 3
    assert lockout.frozen is True


def test_freeze_latches() -> None:
    lockout = LockoutCounter()
    for _ in range(3):
        lockout.record(3)
    assert lockout.frozen is True
    lockout.record(99)  # already latched; stays frozen regardless of later counts
    assert lockout.frozen is True
