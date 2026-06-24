"""Break-glass config validation — disabled-by-default and refuse-to-boot when misconfigured."""

from collections.abc import Callable

import pytest
from pydantic import SecretStr

from hex.breakglass import BreakGlassConfig, BreakGlassConfigError
from hex.config import Settings


def test_valid_enabled_config_resolves(valid_config: BreakGlassConfig) -> None:
    assert valid_config.enabled is True
    assert valid_config.username == "owner-recovery-7x"
    assert valid_config.password_hash.startswith("$argon2id$")
    assert valid_config.totp_secret


def test_disabled_by_default_needs_no_credential() -> None:
    # A bare Settings (everything default) is disabled and must not raise.
    config = BreakGlassConfig.from_settings(Settings())
    assert config.enabled is False


def test_disabled_with_blank_fields_is_allowed(
    make_settings: Callable[..., Settings],
) -> None:
    config = BreakGlassConfig.from_settings(
        make_settings(
            breakglass_enabled=False,
            breakglass_username="",
            breakglass_password_hash=SecretStr(""),
            breakglass_totp_secret=SecretStr(""),
        )
    )
    assert config.enabled is False


def test_enabled_without_username_refused(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(BreakGlassConfigError, match="USERNAME"):
        BreakGlassConfig.from_settings(make_settings(breakglass_username="  "))


def test_enabled_without_password_hash_refused(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(BreakGlassConfigError, match="PASSWORD_HASH"):
        BreakGlassConfig.from_settings(make_settings(breakglass_password_hash=SecretStr("")))


def test_enabled_with_non_argon2id_hash_refused(make_settings: Callable[..., Settings]) -> None:
    # A bcrypt-shaped hash (or anything not Argon2id) is rejected.
    with pytest.raises(BreakGlassConfigError, match="PASSWORD_HASH"):
        BreakGlassConfig.from_settings(
            make_settings(breakglass_password_hash=SecretStr("$2b$12$abcdefghijklmnopqrstuv"))
        )


def test_enabled_with_argon2i_hash_refused(make_settings: Callable[..., Settings]) -> None:
    # Argon2i/Argon2d are not accepted — Argon2id specifically.
    with pytest.raises(BreakGlassConfigError, match="PASSWORD_HASH"):
        BreakGlassConfig.from_settings(
            make_settings(breakglass_password_hash=SecretStr("$argon2i$v=19$m=65536,t=3,p=1$x$y"))
        )


def test_enabled_without_totp_refused(make_settings: Callable[..., Settings]) -> None:
    # MFA is mandatory when enabled (SECURITY_MODEL §13).
    with pytest.raises(BreakGlassConfigError, match="TOTP"):
        BreakGlassConfig.from_settings(make_settings(breakglass_totp_secret=SecretStr("")))


def test_enabled_with_non_base32_totp_refused(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(BreakGlassConfigError, match="TOTP"):
        BreakGlassConfig.from_settings(
            make_settings(breakglass_totp_secret=SecretStr("not base32!"))
        )


def test_enabled_with_short_totp_seed_refused(make_settings: Callable[..., Settings]) -> None:
    # Valid base32 but only 40 bits — below the 128-bit floor, brute-forceable offline.
    with pytest.raises(BreakGlassConfigError, match="TOTP"):
        BreakGlassConfig.from_settings(make_settings(breakglass_totp_secret=SecretStr("AAAAAAAA")))


def test_local_only_defaults_true(valid_config: BreakGlassConfig) -> None:
    # The contract Slice 4-2's LAN-only listener will enforce.
    assert valid_config.local_only is True


def test_secrets_excluded_from_repr(valid_config: BreakGlassConfig) -> None:
    # The hash and TOTP seed must never leak through a stray repr/log line.
    rendered = repr(valid_config)
    assert valid_config.password_hash not in rendered
    assert valid_config.totp_secret not in rendered
