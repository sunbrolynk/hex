"""Offline TOTP verification: current code, ±1 step drift tolerance, and fail-secure rejects."""

import pyotp

from hex.breakglass.totp import verify_totp

_T = 1_700_000_000  # fixed epoch → deterministic codes


def _wrong_code(secret: str) -> str:
    """A 6-digit code guaranteed not to match the current step or either drift neighbour."""
    valid = {pyotp.TOTP(secret).at(_T + d) for d in (-30, 0, 30)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


def test_accepts_current_code() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, pyotp.TOTP(secret).at(_T), for_time=_T) is True


def test_accepts_one_step_drift() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, pyotp.TOTP(secret).at(_T - 30), for_time=_T) is True


def test_rejects_beyond_drift_window() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, pyotp.TOTP(secret).at(_T - 90), for_time=_T) is False


def test_rejects_wrong_code() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, _wrong_code(secret), for_time=_T) is False


def test_rejects_empty_code_or_secret() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, "", for_time=_T) is False
    assert verify_totp("", "123456", for_time=_T) is False


def test_fails_secure_on_degenerate_time() -> None:
    # A non-positive epoch makes pyotp raise; verify_totp must swallow it and return False.
    secret = pyotp.random_base32()
    assert verify_totp(secret, "123456", for_time=0) is False
