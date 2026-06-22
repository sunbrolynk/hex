"""Shared OIDC test helpers: a local RSA signer, JWKS, and minted ID tokens."""

import base64
import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import SecretStr

from hex.config import Settings

BASE = "http://auth.test"
SLUG = "hex"
CLIENT_ID = "hex-client"
KID = "test-key-1"
ISS = f"{BASE}/application/o/{SLUG}/"
DISCOVERY_URL = f"{BASE}/application/o/{SLUG}/.well-known/openid-configuration"
AUTHORIZE_URL = f"{BASE}/application/o/authorize/"
TOKEN_URL = f"{BASE}/application/o/token/"
JWKS_URL = f"{BASE}/application/o/{SLUG}/jwks/"
END_SESSION_URL = f"{BASE}/application/o/{SLUG}/end-session/"
NONCE = "nonce-under-test"

# One keypair for the whole test module — RSA generation is the expensive part.
_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # for signature-mismatch


def settings_oidc(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "authentik_base_url": BASE,
        "authentik_oidc_client_id": CLIENT_ID,
        "authentik_oidc_client_secret": SecretStr("client-secret"),
        "authentik_oidc_app_slug": SLUG,
    }
    return Settings(**(base | overrides))


def discovery_doc(**overrides: Any) -> dict[str, Any]:
    doc = {
        "issuer": ISS,
        "authorization_endpoint": AUTHORIZE_URL,
        "token_endpoint": TOKEN_URL,
        "jwks_uri": JWKS_URL,
        "end_session_endpoint": END_SESSION_URL,
    }
    return doc | overrides


def jwks_dict(*, kid: str = KID, priv: rsa.RSAPrivateKey | None = None) -> dict[str, Any]:
    pub = (priv or _PRIV).public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk |= {"kid": kid, "use": "sig", "alg": "RS256"}
    return {"keys": [jwk]}


def id_token(
    *,
    iss: str = ISS,
    aud: str = CLIENT_ID,
    sub: str = "ak-user-1",
    nonce: str = NONCE,
    email: str | None = "owner@example.com",
    exp_delta: int = 300,
    kid: str | None = KID,
    priv: rsa.RSAPrivateKey | None = None,
    **extra: Any,
) -> str:
    now = int(time.time())
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "nonce": nonce,
        "email": email,
        "preferred_username": "owner",
        "iat": now,
        "exp": now + exp_delta,
        **extra,
    }
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(payload, priv or _PRIV, algorithm="RS256", headers=headers)


def alg_none_token(*, kid: str | None = KID, **claims: Any) -> str:
    """A hand-crafted unsigned (alg=none) token — must be rejected."""
    now = int(time.time())
    payload = {
        "iss": ISS,
        "aud": CLIENT_ID,
        "sub": "x",
        "nonce": NONCE,
        "iat": now,
        "exp": now + 300,
    } | claims
    header: dict[str, Any] = {"alg": "none", "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid

    def seg(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg(header)}.{seg(payload)}."


def other_key() -> rsa.RSAPrivateKey:
    """A different private key, for forging a signature that JWKS won't verify."""
    return _OTHER
