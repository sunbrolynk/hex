"""PKCE + CSRF helpers for the Authorization-Code flow (RFC 7636, OIDC core)."""

import base64
import hashlib
import secrets

_VERIFIER_BYTES = 48  # → 64 url-safe chars, within RFC 7636's 43–128 range


def make_state() -> str:
    """High-entropy CSRF state for the authorize round-trip."""
    return secrets.token_urlsafe(32)


def make_nonce() -> str:
    """High-entropy nonce binding the ID token to this login attempt."""
    return secrets.token_urlsafe(32)


def make_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256."""
    verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
