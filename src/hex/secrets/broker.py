"""Secrets broker — envelope encryption for secrets at rest (docs/SECRETS.md).

A per-record random data-encryption key (DEK) encrypts the payload with AES-256-GCM; the DEK
is then wrapped by the key-encryption key (KEK), also AES-256-GCM. The KEK comes from config
(injected env for now; a KMS/Vault source can replace it without changing callers).
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from hex.config import Settings
from hex.secrets.errors import InsecureConfigError, InvalidToken

_KEK_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard nonce
_WRAPPED_DEK_BYTES = 32 + 16  # 256-bit DEK + GCM tag
_VERSION = b"\x01"
_HEADER = 1 + _NONCE_BYTES + _WRAPPED_DEK_BYTES + _NONCE_BYTES

_KEK_HELP = (
    "HEX_KEK must be base64 of 32 random bytes. Generate: "
    'python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"'
)


class SecretsBroker:
    """Envelope-encrypts/decrypts secrets with a config-supplied KEK."""

    def __init__(self, kek_b64: str) -> None:
        """Initialize from a base64 KEK.

        Raises:
            InsecureConfigError: If the KEK is not valid base64 or not 32 bytes.
        """
        try:
            kek = base64.b64decode(kek_b64, validate=True)
        except ValueError as exc:
            raise InsecureConfigError(_KEK_HELP) from exc
        if len(kek) != _KEK_BYTES:
            raise InsecureConfigError(_KEK_HELP)
        self._kek = AESGCM(kek)

    def encrypt(self, plaintext: str | bytes) -> str:
        """Envelope-encrypt and return a base64 token."""
        # A fresh DEK per record means the data layer never reuses a (key, nonce). The KEK is
        # long-lived, so its random 96-bit nonce is safe only to the birthday bound (~2^32
        # wraps); rotate the KEK well before that. The version byte is not yet bound as AAD —
        # do so when a v2 format lands.
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        dek = AESGCM.generate_key(bit_length=256)
        dek_nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(dek_nonce, data, None)
        kek_nonce = os.urandom(_NONCE_BYTES)
        wrapped = self._kek.encrypt(kek_nonce, dek, None)
        return base64.b64encode(_VERSION + kek_nonce + wrapped + dek_nonce + ciphertext).decode()

    def decrypt(self, token: str) -> bytes:
        """Decrypt an envelope token.

        Raises:
            InvalidToken: If the token is malformed, truncated, tampered, or was produced
                under a different KEK.
        """
        try:
            blob = base64.b64decode(token, validate=True)
        except ValueError as exc:
            raise InvalidToken("malformed token") from exc
        if len(blob) < _HEADER or blob[0:1] != _VERSION:
            raise InvalidToken("unrecognized or truncated token")
        kek_nonce = blob[1 : 1 + _NONCE_BYTES]
        wrapped = blob[1 + _NONCE_BYTES : 1 + _NONCE_BYTES + _WRAPPED_DEK_BYTES]
        dek_nonce = blob[1 + _NONCE_BYTES + _WRAPPED_DEK_BYTES : _HEADER]
        ciphertext = blob[_HEADER:]
        try:
            dek = self._kek.decrypt(kek_nonce, wrapped, None)
            return AESGCM(dek).decrypt(dek_nonce, ciphertext, None)
        except (InvalidTag, ValueError) as exc:
            # InvalidTag = tamper/wrong-KEK; ValueError = any other malformed input.
            raise InvalidToken("authentication failed (tampered or wrong KEK)") from exc


def broker_from_settings(settings: Settings) -> SecretsBroker:
    """Build a broker from the configured KEK (validates it; refuse to boot on failure)."""
    return SecretsBroker(settings.kek.get_secret_value())
