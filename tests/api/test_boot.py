"""Refuse-to-boot integration: create_app validates secrets."""

import base64
import secrets

import pyotp
import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from hex.api.main import create_app
from hex.breakglass import BreakGlassConfigError
from hex.config import Settings
from hex.secrets.errors import InsecureConfigError


def _valid_settings(**overrides: SecretStr) -> Settings:
    base = {
        "secret_key": SecretStr(secrets.token_urlsafe(64)),
        "kek": SecretStr(base64.b64encode(secrets.token_bytes(32)).decode()),
        "db_password": SecretStr(secrets.token_urlsafe(32)),
        "proxy_shared_secret": SecretStr(secrets.token_urlsafe(48)),
        "audit_key": SecretStr(secrets.token_urlsafe(48)),
    }
    return Settings.model_validate(base | overrides)


def test_create_app_refuses_weak_secret() -> None:
    with pytest.raises(InsecureConfigError):
        create_app(_valid_settings(secret_key=SecretStr("changeme")))


def test_create_app_refuses_missing_audit_key() -> None:
    with pytest.raises(InsecureConfigError):
        create_app(_valid_settings(audit_key=SecretStr("")))


def test_create_app_boots_with_valid_secrets() -> None:
    app = create_app(_valid_settings())
    assert app.title == "HEx"


def test_create_app_refuses_enabled_breakglass_without_credential() -> None:
    # Break-glass enabled but the passphrase hash is missing → refuse to boot (ADR 0008).
    broken = _valid_settings().model_copy(
        update={"breakglass_enabled": True, "breakglass_username": "owner-recovery-7x"}
    )
    with pytest.raises(BreakGlassConfigError):
        create_app(broken)


def test_create_app_boots_with_valid_breakglass() -> None:
    hasher = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1)
    configured = _valid_settings().model_copy(
        update={
            "breakglass_enabled": True,
            "breakglass_username": "owner-recovery-7x",
            "breakglass_password_hash": SecretStr(hasher.hash("recovery-passphrase")),
            "breakglass_totp_secret": SecretStr(pyotp.random_base32()),
        }
    )
    app = create_app(configured)
    assert app.state.breakglass.enabled is True
