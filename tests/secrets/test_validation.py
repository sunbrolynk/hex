"""Boot-time secret validation (refuse-to-boot) tests."""

import base64
import secrets

import pytest
from pydantic import SecretStr

from hex.config import Settings
from hex.secrets.errors import InsecureConfigError
from hex.secrets.validation import validate_secrets

_FIELDS = ["secret_key", "kek", "db_password", "proxy_shared_secret"]


def _valid() -> dict[str, SecretStr]:
    return {
        "secret_key": SecretStr(secrets.token_urlsafe(64)),
        "kek": SecretStr(base64.b64encode(secrets.token_bytes(32)).decode()),
        "db_password": SecretStr(secrets.token_urlsafe(32)),
        "proxy_shared_secret": SecretStr(secrets.token_urlsafe(48)),
    }


def _settings(**overrides: SecretStr) -> Settings:
    return Settings.model_validate(_valid() | overrides)


def test_valid_secrets_pass() -> None:
    validate_secrets(_settings())  # no raise


@pytest.mark.parametrize("field", _FIELDS)
def test_missing_secret_refused(field: str) -> None:
    with pytest.raises(InsecureConfigError):
        validate_secrets(_settings(**{field: SecretStr("")}))


@pytest.mark.parametrize("field", _FIELDS)
def test_short_secret_refused(field: str) -> None:
    with pytest.raises(InsecureConfigError):
        validate_secrets(_settings(**{field: SecretStr("short")}))


@pytest.mark.parametrize("placeholder", ["changeme", "your-secret-key", "password123"])
def test_placeholder_secret_refused(placeholder: str) -> None:
    padded = placeholder + "x" * 60  # long enough that the denylist, not length, triggers
    with pytest.raises(InsecureConfigError):
        validate_secrets(_settings(secret_key=SecretStr(padded)))


def test_error_names_var_but_never_the_value() -> None:
    leaked = "changeme" + "z" * 60
    with pytest.raises(InsecureConfigError) as exc:
        validate_secrets(_settings(secret_key=SecretStr(leaked)))
    message = str(exc.value)
    assert "HEX_SECRET_KEY" in message
    assert leaked not in message
