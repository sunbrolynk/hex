"""Secrets broker (envelope encryption) tests."""

import base64
import secrets

import pytest

from hex.secrets.broker import SecretsBroker
from hex.secrets.errors import InsecureConfigError, InvalidToken


def _kek() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


def test_round_trip_str() -> None:
    broker = SecretsBroker(_kek())
    token = broker.encrypt("super-secret-value")
    assert broker.decrypt(token) == b"super-secret-value"


def test_round_trip_bytes() -> None:
    broker = SecretsBroker(_kek())
    assert broker.decrypt(broker.encrypt(b"\x00\x01raw")) == b"\x00\x01raw"


def test_ciphertext_does_not_leak_plaintext() -> None:
    broker = SecretsBroker(_kek())
    token = broker.encrypt("look-for-me")
    assert "look-for-me" not in token
    assert b"look-for-me" not in base64.b64decode(token)


def test_tampered_token_rejected() -> None:
    broker = SecretsBroker(_kek())
    raw = bytearray(base64.b64decode(broker.encrypt("x")))
    raw[-1] ^= 0x01  # flip a ciphertext bit
    with pytest.raises(InvalidToken):
        broker.decrypt(base64.b64encode(bytes(raw)).decode())


def test_wrong_kek_cannot_decrypt() -> None:
    token = SecretsBroker(_kek()).encrypt("x")
    with pytest.raises(InvalidToken):
        SecretsBroker(_kek()).decrypt(token)  # different KEK


def test_malformed_tokens_rejected() -> None:
    broker = SecretsBroker(_kek())
    with pytest.raises(InvalidToken):
        broker.decrypt("!!! not base64 !!!")
    with pytest.raises(InvalidToken):
        broker.decrypt(base64.b64encode(b"short").decode())


def test_bad_kek_rejected() -> None:
    with pytest.raises(InsecureConfigError):
        SecretsBroker("not-valid-base64!!!")
    with pytest.raises(InsecureConfigError):
        SecretsBroker(base64.b64encode(secrets.token_bytes(16)).decode())  # wrong length
