"""First-run setup token — an out-of-band capability for the bootstrap surface.

The token is high-entropy (≥256 bits), so a single SHA-256 is the right at-rest form: there is
nothing to brute-force, and we want constant-time comparison without Argon2's cost. (Argon2id is
for the low-entropy break-glass password, not this.) Only the hash is stored; the plaintext is
shown once in the container logs (docs/BOOTSTRAP.md, non-negotiable 5).
"""

import hashlib
import hmac
import secrets

_TOKEN_BYTES = 32  # 256 bits of entropy
# Comparison target when no token is on file, so verify timing doesn't reveal that fact.
_DUMMY_HASH = "0" * 64


def mint_token() -> str:
    """A fresh URL-safe setup token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, stored_hash: str | None) -> bool:
    """Constant-time check of ``token`` against a stored hash.

    Always hashes and compares — even when no token is on file — so a caller cannot learn from
    timing whether one was issued. Returns False (fail-secure) when ``stored_hash`` is None.
    """
    candidate = hash_token(token)
    if stored_hash is None:
        hmac.compare_digest(candidate, _DUMMY_HASH)  # decoy compare keeps timing uniform
        return False
    return hmac.compare_digest(candidate, stored_hash)
