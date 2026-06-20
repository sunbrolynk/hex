"""Refuse-to-boot integration: create_app validates secrets."""

import base64
import secrets

import pytest
from pydantic import SecretStr

from hex.api.main import create_app
from hex.config import Settings
from hex.secrets.errors import InsecureConfigError


def _valid_settings(**overrides: SecretStr) -> Settings:
    base = {
        "secret_key": SecretStr(secrets.token_urlsafe(64)),
        "kek": SecretStr(base64.b64encode(secrets.token_bytes(32)).decode()),
        "db_password": SecretStr(secrets.token_urlsafe(32)),
        "proxy_shared_secret": SecretStr(secrets.token_urlsafe(48)),
    }
    return Settings.model_validate(base | overrides)


def test_create_app_refuses_weak_secret() -> None:
    with pytest.raises(InsecureConfigError):
        create_app(_valid_settings(secret_key=SecretStr("changeme")))


def test_create_app_boots_with_valid_secrets() -> None:
    app = create_app(_valid_settings())
    assert app.title == "HEx"
