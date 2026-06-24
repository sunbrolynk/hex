"""Shared break-glass test factories: a known-good enabled credential."""

from collections.abc import Callable
from typing import Any

import pyotp
import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from hex.breakglass import BreakGlassConfig
from hex.config import Settings

PASSPHRASE = "correct horse battery staple"
FOR_TIME = 1_700_000_000  # fixed epoch so TOTP generation/verification stays deterministic


@pytest.fixture(scope="session")
def totp_secret() -> str:
    return pyotp.random_base32()


@pytest.fixture(scope="session")
def password_hash() -> str:
    return PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1).hash(PASSPHRASE)


@pytest.fixture
def make_settings(password_hash: str, totp_secret: str) -> Callable[..., Settings]:
    """Build Settings with a valid enabled break-glass config; override any field per test."""

    def _make(**overrides: Any) -> Settings:
        base: dict[str, Any] = {
            "breakglass_enabled": True,
            "breakglass_username": "owner-recovery-7x",
            "breakglass_password_hash": SecretStr(password_hash),
            "breakglass_totp_secret": SecretStr(totp_secret),
        }
        return Settings.model_validate(base | overrides)

    return _make


@pytest.fixture
def valid_config(make_settings: Callable[..., Settings]) -> BreakGlassConfig:
    return BreakGlassConfig.from_settings(make_settings())


@pytest.fixture
def valid_totp(totp_secret: str) -> str:
    return pyotp.TOTP(totp_secret).at(FOR_TIME)


@pytest.fixture
def wrong_totp(totp_secret: str) -> str:
    """A 6-digit code guaranteed not to match the current step or either ±30s drift neighbour."""
    valid = {pyotp.TOTP(totp_secret).at(FOR_TIME + d) for d in (-30, 0, 30)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)
