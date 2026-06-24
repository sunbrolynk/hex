"""Break-glass configuration view (ADR 0008, SECURITY_MODEL §13). Disabled by default.

When enabled, the credential must be *completely* configured or HEx refuses to boot — a
half-configured emergency door is worse than none. Validation is non-leaky: it names the
offending variable and how to set it, never a secret value.
"""

import base64
import binascii
from dataclasses import dataclass, field

from hex.config import Settings


class BreakGlassConfigError(ValueError):
    """Break-glass is enabled but incompletely or insecurely configured — refuse to boot."""


@dataclass(frozen=True)
class BreakGlassConfig:
    """Resolved break-glass settings. ``enabled=False`` means no local login path exists."""

    enabled: bool
    require_idp_down: bool
    local_only: bool
    username: str
    password_hash: str = field(repr=False)  # Argon2id PHC string; "" when disabled
    totp_secret: str = field(repr=False)  # base32 TOTP seed; "" when disabled

    @classmethod
    def from_settings(cls, settings: Settings) -> "BreakGlassConfig":
        """Build and validate. Raises ``BreakGlassConfigError`` on an enabled-but-broken config."""
        enabled = settings.breakglass_enabled
        username = settings.breakglass_username.strip()
        password_hash = settings.breakglass_password_hash.get_secret_value()
        totp_secret = settings.breakglass_totp_secret.get_secret_value().strip()

        if enabled:
            if not username:
                raise BreakGlassConfigError(
                    "HEX_BREAKGLASS_ENABLED=true but HEX_BREAKGLASS_USERNAME is empty. "
                    "Set a neutral, non-obvious username."
                )
            # Argon2id specifically — reject argon2i/argon2d and any non-Argon2 string.
            if not password_hash.startswith("$argon2id$"):
                raise BreakGlassConfigError(
                    "HEX_BREAKGLASS_PASSWORD_HASH must be an Argon2id hash (starts with "
                    "'$argon2id$'). Generate it with: python -c \"from argon2 import "
                    "PasswordHasher; import getpass; print(PasswordHasher(memory_cost=65536, "
                    'time_cost=3, parallelism=1).hash(getpass.getpass()))"'
                )
            # MFA is mandatory when enabled (SECURITY_MODEL §13): no MFA-less emergency door.
            # Require ≥128-bit entropy so a too-short seed can't be brute-forced offline.
            if not _is_strong_base32_seed(totp_secret):
                raise BreakGlassConfigError(
                    "HEX_BREAKGLASS_TOTP_SECRET must be a base32 TOTP seed of at least 128 bits "
                    "(MFA is required when break-glass is enabled). Generate it with: python -c "
                    '"import pyotp; print(pyotp.random_base32())"'
                )

        return cls(
            enabled=enabled,
            require_idp_down=settings.breakglass_require_idp_down,
            local_only=settings.breakglass_local_only,
            username=username,
            password_hash=password_hash,
            totp_secret=totp_secret,
        )


_MIN_TOTP_SEED_BYTES = 16  # 128 bits — the entropy floor for the offline MFA seed


def _is_strong_base32_seed(value: str) -> bool:
    """True if ``value`` is base32 (RFC 4648, case-insensitive) decoding to ≥128 bits."""
    if not value:
        return False
    try:
        decoded = base64.b32decode(value, casefold=True)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) >= _MIN_TOTP_SEED_BYTES
