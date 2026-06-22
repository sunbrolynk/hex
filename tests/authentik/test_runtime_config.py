"""resolve_oidc_config: env-over-DB precedence, secret decryption, and fail-secure edges."""

import base64
import os

import pytest

from hex.authentik import resolve_oidc_config
from hex.database.models import AuthentikIntegration
from hex.secrets.broker import SecretsBroker
from hex.secrets.errors import InvalidToken
from tests.conftest import make_settings


def _broker() -> SecretsBroker:
    return SecretsBroker(base64.b64encode(os.urandom(32)).decode())


def test_env_values_configure_without_a_db_row() -> None:
    settings = make_settings(
        authentik_base_url="http://env",
        authentik_oidc_client_id="env-id",
        authentik_oidc_client_secret="env-secret",
    )
    cfg = resolve_oidc_config(settings, None, _broker())
    assert cfg.oidc_configured
    assert cfg.authentik_base_url == "http://env"
    assert cfg.authentik_oidc_client_id == "env-id"
    assert cfg.authentik_oidc_client_secret.get_secret_value() == "env-secret"


def test_db_row_used_and_secret_decrypted_when_env_empty() -> None:
    broker = _broker()
    row = AuthentikIntegration(
        id=1,
        base_url="http://db",
        internal_base_url="http://db-internal",
        client_id="db-id",
        client_secret_enc=broker.encrypt("db-secret"),
        provider_pk=7,
        app_slug="hex",
    )
    cfg = resolve_oidc_config(make_settings(), row, broker)
    assert cfg.oidc_configured
    assert cfg.authentik_base_url == "http://db"
    assert cfg.authentik_server_base_url == "http://db-internal"
    assert cfg.authentik_oidc_client_id == "db-id"
    assert cfg.authentik_oidc_client_secret.get_secret_value() == "db-secret"


def test_unconfigured_when_neither_env_nor_db() -> None:
    cfg = resolve_oidc_config(make_settings(), None, _broker())
    assert not cfg.oidc_configured


def test_env_overrides_per_field_with_db_fallback() -> None:
    broker = _broker()
    row = AuthentikIntegration(
        id=1, base_url="http://db", client_id="db-id", client_secret_enc=broker.encrypt("db-secret")
    )
    # Only the base URL is set in env; client id + secret fall back to the DB row.
    settings = make_settings(authentik_base_url="http://env")
    cfg = resolve_oidc_config(settings, row, broker)
    assert cfg.authentik_base_url == "http://env"
    assert cfg.authentik_oidc_client_id == "db-id"
    assert cfg.authentik_oidc_client_secret.get_secret_value() == "db-secret"


def test_env_secret_wins_and_db_is_not_decrypted() -> None:
    broker = _broker()
    row = AuthentikIntegration(
        id=1,
        base_url="http://db",
        client_id="db-id",
        client_secret_enc=broker.encrypt("db-secret"),
    )
    settings = make_settings(
        authentik_base_url="http://env",
        authentik_oidc_client_id="env-id",
        authentik_oidc_client_secret="env-secret",
    )
    cfg = resolve_oidc_config(settings, row, broker)
    assert cfg.authentik_oidc_client_secret.get_secret_value() == "env-secret"


def test_undecryptable_db_secret_raises_invalid_token() -> None:
    # Malformed/tampered token → InvalidToken; the dependency turns this into a 503.
    row = AuthentikIntegration(
        id=1, base_url="http://db", client_id="db-id", client_secret_enc="garbage"
    )
    with pytest.raises(InvalidToken):
        resolve_oidc_config(make_settings(), row, _broker())


def test_secret_encrypted_under_a_different_kek_raises_invalid_token() -> None:
    # The "rotated/wrong KEK" case the docstrings cite — a valid envelope from another KEK hits
    # the GCM auth-tag failure branch, distinct from the malformed-token path above.
    writer, reader = _broker(), _broker()  # two independent random KEKs
    row = AuthentikIntegration(
        id=1, base_url="http://db", client_id="db-id", client_secret_enc=writer.encrypt("db-secret")
    )
    with pytest.raises(InvalidToken):
        resolve_oidc_config(make_settings(), row, reader)


def test_partial_db_row_without_secret_is_unconfigured_and_skips_decrypt() -> None:
    # Bootstrap half-wrote the row (base_url + client_id, no secret yet): resolve to unconfigured
    # WITHOUT attempting to decrypt a missing blob.
    class _NoDecrypt(SecretsBroker):
        def decrypt(self, token: str) -> bytes:
            raise AssertionError("decrypt must not run when no secret blob exists")

    broker = _NoDecrypt(base64.b64encode(os.urandom(32)).decode())
    row = AuthentikIntegration(
        id=1, base_url="http://db", client_id="db-id", client_secret_enc=None
    )
    cfg = resolve_oidc_config(make_settings(), row, broker)
    assert not cfg.oidc_configured


def test_db_app_slug_is_ignored_in_favor_of_env() -> None:
    # app_slug is authoritative from env (default "hex"); a divergent DB value must not take effect.
    broker = _broker()
    row = AuthentikIntegration(
        id=1,
        base_url="http://db",
        client_id="db-id",
        client_secret_enc=broker.encrypt("s"),
        app_slug="some-other-slug",
    )
    cfg = resolve_oidc_config(make_settings(), row, broker)
    assert cfg.authentik_oidc_app_slug == "hex"
